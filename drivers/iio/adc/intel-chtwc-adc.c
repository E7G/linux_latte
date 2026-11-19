// SPDX-License-Identifier: GPL-2.0-only
/*
 * Intel Cherry Trail Whiskey Cove GPADC.
 * Register/channel definitions based on Intel's GPLv2 Android driver,
 * copyright (C) 2013-2015 Intel Corporation, in Xiaomi's Mi Pad2 tree.
 *
 * On-demand acquisition and optional factory LPAT board-NTC conversion. Does
 * not enable a thermal OpRegion, rewrite monitors or replace charger/BCU policy.
 */
#include <linux/acpi.h>
#include <linux/atomic.h>
#include <linux/completion.h>
#include <linux/iio/driver.h>
#include <linux/iio/iio.h>
#include <linux/iio/machine.h>
#include <linux/interrupt.h>
#include <linux/mfd/intel_soc_pmic.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/regmap.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/sysfs.h>

#include "intel-chtwc-adc-core.h"
#include "intel-chtwc-adc-lpat.h"

struct chtwc_adc {
	struct device *dev;
	struct regmap *regmap;
	struct mutex lock;
	struct completion completion;
	struct chtwc_adc_io io;
	struct chtwc_adc_lpat_point *lpat;
	unsigned int lpat_count;
	atomic_t irq_enabled;
	int irq;
	int irq_error;
	unsigned int expected;
	unsigned int saved_mask;
	bool mask_owned;
	bool suspended;
	bool removing;
	bool faulted;
	struct iio_chan_spec channels[];
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

	if (mask != IIO_CHAN_INFO_RAW && mask != IIO_CHAN_INFO_PROCESSED)
		return -EINVAL;
	if (mask == IIO_CHAN_INFO_PROCESSED && channel->type != IIO_RESISTANCE &&
	    (channel->type != IIO_TEMP || !adc->lpat ||
	     channel->channel < 5 || channel->channel > 7))
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
			if (mask == IIO_CHAN_INFO_PROCESSED && channel->type == IIO_TEMP)
				ret = chtwc_adc_temperature(channel->channel, &sample,
							    adc->lpat, adc->lpat_count, val);
			else if (mask == IIO_CHAN_INFO_PROCESSED)
				ret = chtwc_adc_resistance(channel->channel, &sample, val);
			else
				*val = sample.count;
			if (!ret)
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

/* Separate resistance aliases retain existing in_tempN_raw paths unchanged. */
#define CHTWC_RESISTANCE(_index, _label) { \
	.type = IIO_RESISTANCE, .indexed = 1, .channel = (_index), \
	.datasheet_name = (_label), \
	.info_mask_separate = BIT(IIO_CHAN_INFO_RAW) | BIT(IIO_CHAN_INFO_PROCESSED), \
}

static const struct iio_chan_spec chtwc_iio_channels[] = {
	CHTWC_CHANNEL(IIO_VOLTAGE, 0, "VBAT"),
	CHTWC_RESISTANCE(1, "BATID"),
	CHTWC_CHANNEL(IIO_TEMP, 2, "PMICTEMP"),
	CHTWC_CHANNEL(IIO_TEMP, 3, "BATTEMP0"),
	CHTWC_CHANNEL(IIO_TEMP, 4, "BATTEMP1"),
	CHTWC_CHANNEL(IIO_TEMP, 5, "SYSTEMP0"),
	CHTWC_CHANNEL(IIO_TEMP, 6, "SYSTEMP1"),
	CHTWC_CHANNEL(IIO_TEMP, 7, "SYSTEMP2"),
	CHTWC_RESISTANCE(8, "USBID"),
	CHTWC_CHANNEL(IIO_VOLTAGE, 9, "PEAK"),
	CHTWC_CHANNEL(IIO_VOLTAGE, 10, "AGND"),
	CHTWC_RESISTANCE(3, "BATTEMP0"),
	CHTWC_RESISTANCE(4, "BATTEMP1"),
	CHTWC_RESISTANCE(5, "SYSTEMP0"),
	CHTWC_RESISTANCE(6, "SYSTEMP1"),
	CHTWC_RESISTANCE(7, "SYSTEMP2"),
};
static_assert(ARRAY_SIZE(chtwc_iio_channels) == ARRAY_SIZE(chtwc_adc_channels) + 5);

/*
 * The Mi Pad2 PMIC's constant LPAT maps ohms to decikelvin returned directly
 * through the firmware _TMP path. This is NOT the centi-Celsius LPAT used by
 * INT340x. Do not execute a method, force AML availability gates or copy the
 * generic LPAT parser's unchecked u64-to-int truncation here.
 * An unavailable/malformed table leaves all existing raw/ohms paths intact.
 */
static int chtwc_adc_load_lpat(struct chtwc_adc *adc)
{
	struct acpi_buffer buffer = { ACPI_ALLOCATE_BUFFER, NULL };
	struct chtwc_adc_lpat_point *points;
	union acpi_object *object, *elements;
	acpi_handle parent = ACPI_HANDLE(adc->dev->parent), handle;
	unsigned int count, i;
	acpi_object_type type;
	acpi_status status;
	int ret = 0;

	if (!parent || ACPI_FAILURE(acpi_get_handle(parent, "LPAT", &handle)))
		return 0;
	status = acpi_get_type(handle, &type);
	if (ACPI_FAILURE(status) || type != ACPI_TYPE_PACKAGE)
		return 0;
	status = acpi_evaluate_object(handle, NULL, NULL, &buffer);
	if (ACPI_FAILURE(status))
		goto out;
	object = buffer.pointer;
	if (!object || object->type != ACPI_TYPE_PACKAGE ||
	    object->package.count < 4 || object->package.count % 2 ||
	    object->package.count > 2 * CHTWC_LPAT_MAX_POINTS)
		goto out;
	count = object->package.count / 2;
	elements = object->package.elements;
	if (!elements)
		goto out;
	for (i = 0; i < count; i++) {
		if (elements[2 * i].type != ACPI_TYPE_INTEGER ||
		    elements[2 * i + 1].type != ACPI_TYPE_INTEGER ||
		    elements[2 * i].integer.value > INT_MAX / 100 ||
		    elements[2 * i + 1].integer.value > INT_MAX)
			goto out;
	}
	points = devm_kcalloc(adc->dev, count, sizeof(*points), GFP_KERNEL);
	if (!points) {
		ret = -ENOMEM;
		goto out;
	}
	for (i = 0; i < count; i++) {
		points[i].decikelvin = elements[2 * i].integer.value;
		points[i].ohms = elements[2 * i + 1].integer.value;
	}
	if (!chtwc_adc_lpat_valid(points, count)) {
		devm_kfree(adc->dev, points);
		goto out;
	}
	adc->lpat = points;
	adc->lpat_count = count;
out:
	ACPI_FREE(buffer.pointer);
	return ret;
}

static void chtwc_adc_restore_mask(void *data)
{
	struct chtwc_adc *adc = data;
	int ret;

	if (!adc->mask_owned)
		return;
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
	if (adc->mask_owned &&
	    regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK,
			       CHTWC_ADC_OWNED_IRQS, CHTWC_ADC_OWNED_IRQS))
		dev_warn(adc->dev, "Could not quiesce ADC completion sources\n");
	mutex_unlock(&adc->lock);
}

static const struct iio_map chtwc_adc_thermal_maps[] = {
	IIO_MAP("SYSTEMP0", "cht_wcove_thermal", "systemp0"),
	IIO_MAP("SYSTEMP1", "cht_wcove_thermal", "systemp1"),
	IIO_MAP("SYSTEMP2", "cht_wcove_thermal", "systemp2"),
	{ }
};

static void chtwc_adc_remove_thermal(void *data)
{
	platform_device_unregister(data);
}

static int chtwc_adc_add_thermal(struct platform_device *pdev,
				struct iio_dev *indio_dev)
{
	struct device *dev = &pdev->dev;
	struct platform_device *child;
	struct resource resource;
	int irq, ret;

	irq = platform_get_irq_byname(pdev, "thermal");
	if (irq < 0)
		return irq;
	ret = devm_iio_map_array_register(dev, indio_dev, chtwc_adc_thermal_maps);
	if (ret)
		return ret;

	/* A child unbinds and suspends before its ADC provider. */
	resource = (struct resource)DEFINE_RES_IRQ(irq);
	child = platform_device_register_resndata(dev, "cht_wcove_thermal",
						 PLATFORM_DEVID_NONE, &resource,
						 1, NULL, 0);
	if (IS_ERR(child))
		return PTR_ERR(child);

	return devm_add_action_or_reset(dev, chtwc_adc_remove_thermal, child);
}

static int chtwc_adc_probe(struct platform_device *pdev)
{
	struct intel_soc_pmic *pmic = dev_get_drvdata(pdev->dev.parent);
	struct device *dev = &pdev->dev;
	struct iio_dev *indio_dev;
	struct chtwc_adc *adc;
	int ret, i;

	if (pmic->cht_wc_model != INTEL_CHT_WC_XIAOMI_MIPAD2)
		return -ENODEV;
	/* Channel handles can retain the IIO device after driver detach. */
	indio_dev = devm_iio_device_alloc(dev, struct_size(adc, channels,
							 ARRAY_SIZE(chtwc_iio_channels)));
	if (!indio_dev)
		return -ENOMEM;
	adc = iio_priv(indio_dev);
	adc->dev = dev;
	adc->regmap = pmic->regmap;
	ret = chtwc_adc_load_lpat(adc);
	if (ret)
		return ret;
	memcpy(adc->channels, chtwc_iio_channels, sizeof(chtwc_iio_channels));
	if (adc->lpat) {
		for (i = 5; i <= 7; i++)
			adc->channels[i].info_mask_separate |= BIT(IIO_CHAN_INFO_PROCESSED);
	}
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
	ret = devm_request_threaded_irq(dev, adc->irq, NULL, chtwc_adc_irq,
				       IRQF_ONESHOT | IRQF_NO_AUTOEN,
				       dev_name(dev), adc);
	if (ret)
		return dev_err_probe(dev, ret, "Could not request ADC virtual IRQ\n");
	ret = devm_add_action_or_reset(dev, chtwc_adc_quiesce, adc);
	if (ret)
		return ret;
	/*
	 * Claim the exclusive virq before touching masks. On request failure an
	 * existing owner must not see even a temporary mask/preimage restoration.
	 */
	adc->mask_owned = true;
	ret = regmap_update_bits(adc->regmap, CHTWC_ADC_IRQ_MASK,
				 CHTWC_ADC_OWNED_IRQS, CHTWC_ADC_OWNED_IRQS);
	if (ret)
		return ret;
	platform_set_drvdata(pdev, indio_dev);
	indio_dev->name = "cht-whiskey-cove-adc";
	indio_dev->info = &chtwc_adc_info;
	indio_dev->modes = INDIO_DIRECT_MODE;
	indio_dev->channels = adc->channels;
	indio_dev->num_channels = ARRAY_SIZE(chtwc_iio_channels);
	ret = devm_iio_device_register(dev, indio_dev);
	if (ret)
		return ret;
	if (IS_ENABLED(CONFIG_INTEL_CHTWC_THERMAL) && adc->lpat)
		return chtwc_adc_add_thermal(pdev, indio_dev);

	return 0;
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

MODULE_DESCRIPTION("Cherry Trail Whiskey Cove ADC and factory board NTC conversion");
MODULE_LICENSE("GPL");
