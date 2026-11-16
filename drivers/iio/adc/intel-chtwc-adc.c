// SPDX-License-Identifier: GPL-2.0-only
/*
 * Intel Cherry Trail Whiskey Cove GPADC.
 * Register/channel definitions based on Intel's GPLv2 Android driver,
 * copyright (C) 2013-2015 Intel Corporation, in Xiaomi's Mi Pad2 tree.
 *
 * On-demand raw acquisition. Does not enable a thermal OpRegion, rewrite
 * autonomous monitors, calibrate temperatures, or replace charger/BCU policy.
 */
#include <linux/atomic.h>
#include <linux/completion.h>
#include <linux/iio/iio.h>
#include <linux/interrupt.h>
#include <linux/mfd/intel_soc_pmic.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/regmap.h>
#include <linux/sysfs.h>

#include "intel-chtwc-adc-core.h"

struct chtwc_adc {
	struct device *dev;
	struct regmap *regmap;
	struct mutex lock;
	struct completion completion;
	struct chtwc_adc_io io;
	atomic_t irq_enabled;
	int irq;
	int irq_error;
	unsigned int expected;
	unsigned int saved_mask;
	bool suspended;
	bool removing;
	bool faulted;
};

static int chtwc_adc_read(void *context, unsigned int reg, unsigned int *value)
{
	struct chtwc_adc *adc = context;

	return regmap_read(adc->regmap, reg, value);
}

static int chtwc_adc_write(void *context, unsigned int reg, unsigned int value)
{
	struct chtwc_adc *adc = context;

	return regmap_write(adc->regmap, reg, value);
}

static int chtwc_adc_wait_idle(void *context)
{
	struct chtwc_adc *adc = context;
	unsigned int value;

	return regmap_read_poll_timeout(adc->regmap, CHTWC_ADC_REQUEST, value,
				       !(value & CHTWC_ADC_BUSY), 2000, 1000000);
}

/*
 * NO_AUTOEN retains one disabled-depth reference while idle. The handler may
 * claim it without waiting on itself. Process context synchronizes the handler
 * before changing expected/reinitializing the completion.
 */
static void chtwc_adc_stop_irq(struct chtwc_adc *adc)
{
	if (atomic_cmpxchg(&adc->irq_enabled, 1, 0) == 1)
		disable_irq(adc->irq);
	else
		synchronize_irq(adc->irq);
}

static irqreturn_t chtwc_adc_irq(int irq, void *data)
{
	struct chtwc_adc *adc = data;
	int ret;

	ret = chtwc_adc_capture_irq(&adc->io, READ_ONCE(adc->expected));
	if (!ret)
		return IRQ_NONE;
	WRITE_ONCE(adc->irq_error, ret < 0 ? ret : 0);
	if (atomic_cmpxchg(&adc->irq_enabled, 1, 0) == 1)
		disable_irq_nosync(irq);
	complete(&adc->completion);
	return IRQ_HANDLED;
}

static int chtwc_adc_arm(void *context, unsigned int mask)
{
	struct chtwc_adc *adc = context;
	int ret;

	reinit_completion(&adc->completion);
	WRITE_ONCE(adc->irq_error, 0);
	WRITE_ONCE(adc->expected, mask);
	ret = regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK, mask, 0);
	if (ret)
		return ret;
	atomic_set(&adc->irq_enabled, 1);
	/* Only ADC's virtual IRQ; the parent regmap-IRQ chip owns MIRQLVL1. */
	enable_irq(adc->irq);
	return 0;
}

static int chtwc_adc_wait_done(void *context)
{
	struct chtwc_adc *adc = context;

	if (!wait_for_completion_timeout(&adc->completion, msecs_to_jiffies(1000)))
		return -ETIMEDOUT;
	chtwc_adc_stop_irq(adc);
	return READ_ONCE(adc->irq_error);
}

static int chtwc_adc_disarm(void *context, unsigned int mask)
{
	struct chtwc_adc *adc = context;
	unsigned int actual;
	int ret;

	chtwc_adc_stop_irq(adc);
	WRITE_ONCE(adc->expected, 0);
	ret = regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK, mask, mask);
	if (ret)
		return ret;
	ret = regmap_read(adc->regmap, CHTWC_ADC_IRQ_MASK, &actual);
	if (ret)
		return ret;
	return (actual & mask) == mask ? 0 : -EIO;
}

static void chtwc_adc_fault(void *context)
{
	struct chtwc_adc *adc = context;

	adc->faulted = true;
	chtwc_adc_stop_irq(adc);
	/* A timeout/uncertain write must not complete a later transaction. */
	if (regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK,
			       CHTWC_ADC_OWNED_IRQS, CHTWC_ADC_OWNED_IRQS))
		dev_warn_ratelimited(adc->dev, "Could not mask ADC completion sources\n");
	dev_warn_ratelimited(adc->dev, "ADC quarantined after acquisition failure\n");
}

static int chtwc_adc_read_raw(struct iio_dev *indio_dev,
			      const struct iio_chan_spec *channel,
			      int *val, int *val2, long mask)
{
	struct chtwc_adc *adc = iio_priv(indio_dev);
	struct chtwc_adc_sample sample;
	int ret;

	if (mask != IIO_CHAN_INFO_RAW)
		return -EINVAL;
	mutex_lock(&adc->lock);
	if (adc->removing)
		ret = -ENODEV;
	else if (adc->suspended)
		ret = -EBUSY;
	else if (adc->faulted)
		ret = -EIO;
	else {
		ret = chtwc_adc_acquire(&adc->io, channel->channel, &sample);
		if (!ret) {
			*val = sample.count;
			ret = IIO_VAL_INT;
		}
	}
	mutex_unlock(&adc->lock);
	return ret;
}

static int chtwc_adc_read_label(struct iio_dev *indio_dev,
				const struct iio_chan_spec *channel, char *label)
{
	return sysfs_emit(label, "%s\n", channel->datasheet_name);
}

static const struct iio_info chtwc_adc_info = {
	.read_raw = chtwc_adc_read_raw,
	.read_label = chtwc_adc_read_label,
};

#define CHTWC_CHANNEL(_type, _index, _label) { \
	.type = (_type), .indexed = 1, .channel = (_index), \
	.datasheet_name = (_label), .info_mask_separate = BIT(IIO_CHAN_INFO_RAW), \
}

static const struct iio_chan_spec chtwc_iio_channels[] = {
	CHTWC_CHANNEL(IIO_VOLTAGE, 0, "VBAT"),
	CHTWC_CHANNEL(IIO_RESISTANCE, 1, "BATID"),
	CHTWC_CHANNEL(IIO_TEMP, 2, "PMICTEMP"),
	CHTWC_CHANNEL(IIO_TEMP, 3, "BATTEMP0"),
	CHTWC_CHANNEL(IIO_TEMP, 4, "BATTEMP1"),
	CHTWC_CHANNEL(IIO_TEMP, 5, "SYSTEMP0"),
	CHTWC_CHANNEL(IIO_TEMP, 6, "SYSTEMP1"),
	CHTWC_CHANNEL(IIO_TEMP, 7, "SYSTEMP2"),
	CHTWC_CHANNEL(IIO_RESISTANCE, 8, "USBID"),
	CHTWC_CHANNEL(IIO_VOLTAGE, 9, "PEAK"),
	CHTWC_CHANNEL(IIO_VOLTAGE, 10, "AGND"),
};
static_assert(ARRAY_SIZE(chtwc_iio_channels) == ARRAY_SIZE(chtwc_adc_channels));

static void chtwc_adc_restore_mask(void *data)
{
	struct chtwc_adc *adc = data;
	int ret;

	/* Released after free_irq: the IRQ core has disabled the level1 ADC. */
	ret = regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK,
				 CHTWC_ADC_OWNED_IRQS, adc->saved_mask);
	if (ret)
		dev_warn(adc->dev, "Could not restore ADC mask: %d\n", ret);
}

static void chtwc_adc_quiesce(void *data)
{
	struct chtwc_adc *adc = data;

	mutex_lock(&adc->lock);
	adc->removing = true;
	chtwc_adc_stop_irq(adc);
	if (regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK,
			       CHTWC_ADC_OWNED_IRQS, CHTWC_ADC_OWNED_IRQS))
		dev_warn(adc->dev, "Could not quiesce ADC completion sources\n");
	mutex_unlock(&adc->lock);
}

static int chtwc_adc_probe(struct platform_device *pdev)
{
	struct intel_soc_pmic *pmic = dev_get_drvdata(pdev->dev.parent);
	struct device *dev = &pdev->dev;
	struct iio_dev *indio_dev;
	struct chtwc_adc *adc;
	int ret;

	if (pmic->cht_wc_model != INTEL_CHT_WC_XIAOMI_MIPAD2)
		return -ENODEV;
	indio_dev = devm_iio_device_alloc(dev, sizeof(*adc));
	if (!indio_dev)
		return -ENOMEM;
	adc = iio_priv(indio_dev);
	adc->dev = dev;
	adc->regmap = pmic->regmap;
	adc->irq = platform_get_irq(pdev, 0);
	if (adc->irq < 0)
		return adc->irq;
	mutex_init(&adc->lock);
	init_completion(&adc->completion);
	atomic_set(&adc->irq_enabled, 0);
	adc->io = (struct chtwc_adc_io) {
		.context = adc, .read = chtwc_adc_read, .write = chtwc_adc_write,
		.wait_idle = chtwc_adc_wait_idle, .arm = chtwc_adc_arm,
		.wait_done = chtwc_adc_wait_done, .disarm = chtwc_adc_disarm,
		.fault = chtwc_adc_fault,
	};
	ret = regmap_read(adc->regmap, CHTWC_ADC_IRQ_MASK, &adc->saved_mask);
	if (ret)
		return ret;
	/* MCCTICK is not owned here; do not consume/disable another owner. */
	if (!(adc->saved_mask & CHTWC_ADC_TICK_IRQ))
		return dev_err_probe(dev, -EBUSY, "ADC monitor tick has another owner\n");
	ret = devm_add_action_or_reset(dev, chtwc_adc_restore_mask, adc);
	if (ret)
		return ret;
	ret = regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK,
				 CHTWC_ADC_OWNED_IRQS, CHTWC_ADC_OWNED_IRQS);
	if (ret)
		return ret;
	ret = devm_request_threaded_irq(dev, adc->irq, NULL, chtwc_adc_irq,
				       IRQF_ONESHOT | IRQF_NO_AUTOEN,
				       dev_name(dev), adc);
	if (ret)
		return dev_err_probe(dev, ret, "Could not request ADC virtual IRQ\n");
	ret = devm_add_action_or_reset(dev, chtwc_adc_quiesce, adc);
	if (ret)
		return ret;
	platform_set_drvdata(pdev, indio_dev);
	indio_dev->name = "cht-whiskey-cove-adc";
	indio_dev->info = &chtwc_adc_info;
	indio_dev->modes = INDIO_DIRECT_MODE;
	indio_dev->channels = chtwc_iio_channels;
	indio_dev->num_channels = ARRAY_SIZE(chtwc_iio_channels);
	/* No processed/scale interface until physical transfer units are proven. */
	return devm_iio_device_register(dev, indio_dev);
}

static int chtwc_adc_suspend(struct device *dev)
{
	struct chtwc_adc *adc = iio_priv(dev_get_drvdata(dev));
	int ret;

	mutex_lock(&adc->lock);
	ret = chtwc_adc_wait_idle(adc);
	if (!ret) {
		chtwc_adc_stop_irq(adc);
		adc->suspended = true;
	}
	mutex_unlock(&adc->lock);
	return ret;
}

static int chtwc_adc_resume(struct device *dev)
{
	struct chtwc_adc *adc = iio_priv(dev_get_drvdata(dev));

	mutex_lock(&adc->lock);
	adc->suspended = false;
	/* Quarantine survives resume; no silent reissue of an uncertain request. */
	mutex_unlock(&adc->lock);
	return 0;
}
static DEFINE_SIMPLE_DEV_PM_OPS(chtwc_adc_pm_ops, chtwc_adc_suspend, chtwc_adc_resume);

static void chtwc_adc_shutdown(struct platform_device *pdev)
{
	chtwc_adc_quiesce(iio_priv(platform_get_drvdata(pdev)));
}

static const struct platform_device_id chtwc_adc_ids[] = {
	{ "cht_wcove_adc" },
	{ }
};
MODULE_DEVICE_TABLE(platform, chtwc_adc_ids);

static struct platform_driver chtwc_adc_driver = {
	.probe = chtwc_adc_probe,
	.shutdown = chtwc_adc_shutdown,
	.id_table = chtwc_adc_ids,
	.driver = {
		.name = "cht_wcove_adc",
		.pm = pm_sleep_ptr(&chtwc_adc_pm_ops),
	},
};
module_platform_driver(chtwc_adc_driver);

MODULE_DESCRIPTION("Cherry Trail Whiskey Cove on-demand raw ADC");
MODULE_LICENSE("GPL");
