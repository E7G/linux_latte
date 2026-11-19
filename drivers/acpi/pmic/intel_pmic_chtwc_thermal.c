// SPDX-License-Identifier: GPL-2.0-only

#include <linux/atomic.h>
#include <linux/iio/consumer.h>
#include <linux/interrupt.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/regmap.h>
#include <linux/thermal.h>

#include "chtwc_thermal_transport.h"

struct chtwc_thermal {
	struct device *dev;
	struct regmap *regmap;
	struct chtwc_thermal_transport transport;
	atomic_t irq_enabled;
	int irq;
	bool faulted;
};

static int chtwc_thermal_reg_read(void *data, unsigned int reg, unsigned int *value)
{
	struct chtwc_thermal *thermal = data;

	return regmap_read(thermal->regmap, reg, value);
}

static int chtwc_thermal_reg_write(void *data, unsigned int reg, unsigned int value)
{
	struct chtwc_thermal *thermal = data;

	return regmap_write(thermal->regmap, reg, value);
}

static int chtwc_thermal_get_temp(struct thermal_zone_device *zone, int *temp)
{
	struct iio_channel *channel = thermal_zone_device_priv(zone);
	int ret;

	ret = iio_read_channel_attribute(channel, temp, NULL, IIO_CHAN_INFO_PROCESSED);
	if (ret < 0)
		return ret;

	return ret == IIO_VAL_INT ? 0 : -EIO;
}

static const struct thermal_zone_device_ops chtwc_thermal_ops = {
	.get_temp = chtwc_thermal_get_temp,
};

static void chtwc_thermal_unregister_zone(void *data)
{
	thermal_zone_device_unregister(data);
}

static void chtwc_thermal_notify(void *data, const struct chtwc_thermal_packet *packet)
{
	thermal_zone_device_update(data, THERMAL_EVENT_UNSPECIFIED);
}

static int chtwc_thermal_add_zones(struct chtwc_thermal *thermal)
{
	static const char * const channels[] = { "systemp0", "systemp1", "systemp2" };
	static const char * const names[] = { "chtwc-sys0", "chtwc-sys1", "chtwc-sys2" };
	struct device *dev = thermal->dev;
	struct thermal_zone_device *zone;
	struct iio_channel *channel;
	unsigned int i;
	int ret;

	for (i = 0; i < ARRAY_SIZE(channels); i++) {
		channel = devm_iio_channel_get(dev, channels[i]);
		if (IS_ERR(channel))
			return PTR_ERR(channel);
		if (channel->indio_dev != dev_get_drvdata(dev->parent))
			return -ENODEV;

		zone = thermal_tripless_zone_device_register(names[i], channel,
							    &chtwc_thermal_ops, NULL);
		if (IS_ERR(zone))
			return PTR_ERR(zone);
		ret = devm_add_action_or_reset(dev, chtwc_thermal_unregister_zone, zone);
		if (ret)
			return ret;
		ret = thermal_zone_device_enable(zone);
		if (ret)
			return ret;
		ret = chtwc_thermal_transport_consumer(&thermal->transport,
						      CHTWC_THERMAL_SYS0 + i, zone,
						      chtwc_thermal_notify);
		if (ret)
			return ret;
	}

	return 0;
}

static irqreturn_t chtwc_thermal_irq(int irq, void *data)
{
	struct chtwc_thermal *thermal = data;
	int ret;

	ret = chtwc_thermal_transport_capture(&thermal->transport);
	if (ret < 0) {
		WRITE_ONCE(thermal->faulted, true);
		if (atomic_xchg(&thermal->irq_enabled, 0))
			disable_irq_nosync(irq);
		dev_err(thermal->dev, "Thermal IRQ disabled after capture error: %d\n", ret);
	}

	return ret ? IRQ_HANDLED : IRQ_NONE;
}

static void chtwc_thermal_stop(void *data)
{
	struct chtwc_thermal *thermal = data;
	int ret;

	if (atomic_xchg(&thermal->irq_enabled, 0))
		disable_irq(thermal->irq);
	else
		synchronize_irq(thermal->irq);

	ret = chtwc_thermal_transport_stop(&thermal->transport);
	if (ret) {
		WRITE_ONCE(thermal->faulted, true);
		dev_err(thermal->dev, "Could not drain accepted thermal events: %d\n", ret);
	}
}

static void chtwc_thermal_start(struct chtwc_thermal *thermal)
{
	int ret;

	if (READ_ONCE(thermal->faulted))
		return;

	ret = chtwc_thermal_transport_start(&thermal->transport);
	if (ret) {
		/* Board readings are useful even when another source lacks an owner. */
		if (ret == -ENXIO)
			dev_dbg(thermal->dev, "Thermal IRQ left masked: incomplete ownership\n");
		else if (ret != -ENODATA)
			dev_warn(thermal->dev, "Thermal IRQ preflight failed: %d\n", ret);
		return;
	}

	atomic_set(&thermal->irq_enabled, 1);
	enable_irq(thermal->irq);
}

static int chtwc_thermal_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct chtwc_thermal *thermal;
	int ret;

	if (!dev->parent || !dev->parent->parent)
		return -ENODEV;

	thermal = devm_kzalloc(dev, sizeof(*thermal), GFP_KERNEL);
	if (!thermal)
		return -ENOMEM;
	thermal->dev = dev;
	thermal->regmap = dev_get_regmap(dev->parent->parent, NULL);
	if (!thermal->regmap)
		return -ENODEV;

	ret = chtwc_thermal_transport_init(&thermal->transport, thermal,
					   chtwc_thermal_reg_read, chtwc_thermal_reg_write);
	if (ret)
		return ret;
	ret = chtwc_thermal_add_zones(thermal);
	if (ret)
		return dev_err_probe(dev, ret, "Could not register board thermal zones\n");

	thermal->irq = platform_get_irq(pdev, 0);
	if (thermal->irq < 0)
		return thermal->irq;
	ret = devm_request_threaded_irq(dev, thermal->irq, NULL, chtwc_thermal_irq,
					IRQF_NO_AUTOEN | IRQF_ONESHOT, dev_name(dev), thermal);
	if (ret)
		return dev_err_probe(dev, ret, "Could not claim the thermal IRQ\n");
	ret = devm_add_action_or_reset(dev, chtwc_thermal_stop, thermal);
	if (ret)
		return ret;

	platform_set_drvdata(pdev, thermal);
	chtwc_thermal_start(thermal);

	return 0;
}

static int chtwc_thermal_suspend(struct device *dev)
{
	chtwc_thermal_stop(dev_get_drvdata(dev));
	return 0;
}

static int chtwc_thermal_resume(struct device *dev)
{
	chtwc_thermal_start(dev_get_drvdata(dev));
	return 0;
}

static DEFINE_SIMPLE_DEV_PM_OPS(chtwc_thermal_pm_ops, chtwc_thermal_suspend,
			       chtwc_thermal_resume);

static void chtwc_thermal_shutdown(struct platform_device *pdev)
{
	chtwc_thermal_stop(platform_get_drvdata(pdev));
}

static const struct platform_device_id chtwc_thermal_ids[] = {
	{ "cht_wcove_thermal" },
	{ }
};
MODULE_DEVICE_TABLE(platform, chtwc_thermal_ids);

static struct platform_driver chtwc_thermal_driver = {
	.probe = chtwc_thermal_probe,
	.shutdown = chtwc_thermal_shutdown,
	.id_table = chtwc_thermal_ids,
	.driver = {
		.name = "cht_wcove_thermal",
		.pm = pm_sleep_ptr(&chtwc_thermal_pm_ops),
	},
};
module_platform_driver(chtwc_thermal_driver);

MODULE_DESCRIPTION("Xiaomi Mi Pad 2 Cherry Trail Whiskey Cove board thermal sensors");
MODULE_LICENSE("GPL");
