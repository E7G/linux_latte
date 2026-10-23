// SPDX-License-Identifier: GPL-2.0-only
/* Temporary read-only cache vs. hardware audit; no cache replay or register writes. */
#include <linux/device.h>
#include <linux/dmi.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/regmap.h>
#include <sound/soc.h>

static int snapshot(const char *name, const unsigned int *regs, size_t count)
{
	struct snd_soc_component *component;
	struct device *dev;
	unsigned int cache, hw;
	size_t i;
	int ret;

	dev = bus_find_device_by_name(&i2c_bus_type, NULL, name);
	if (!dev)
		return -ENODEV;
	device_lock(dev);
	component = snd_soc_lookup_component(dev, NULL);
	if (!component || !component->regmap) {
		ret = -ENODEV;
		goto out;
	}

	for (i = 0; i < count; i++) {
		ret = regmap_read(component->regmap, regs[i], &cache);
		if (ret)
			goto out;
		ret = regmap_read_bypassed(component->regmap, regs[i], &hw);
		if (ret)
			goto out;
		pr_info("mp2-audio-ro-cont21: %s reg=%03x cache=%04x hw=%04x match=%d\n",
			name, regs[i], cache, hw, cache == hw);
	}
	ret = 0;
out:
	if (ret)
		pr_err("mp2-audio-ro-cont21: %s read failed=%d\n", name, ret);
	device_unlock(dev);
	put_device(dev);
	return ret;
}

static int __init mp2_clock_probe_init(void)
{
	static const unsigned int rt_regs[] = {
		0x2f, 0x61, 0x62, 0x63, 0x64, 0x65, 0x6b,
		0x70, 0x71, 0x73, 0x80, 0x81, 0x82, 0x83,
		0xc0, 0xc1, 0xc2, 0xfa, 0xfb,
	};
	static const unsigned int tfa_regs[] = {
		0x00, 0x03, 0x04, 0x09, 0x0a, 0x80, 0x84,
	};
	int ret;

	if (!dmi_match(DMI_PRODUCT_NAME, "Mipad2") ||
	    !dmi_match(DMI_SYS_VENDOR, "Xiaomi Inc"))
		return -ENODEV;
	ret = snapshot("i2c-10EC5659:01", rt_regs, ARRAY_SIZE(rt_regs));
	if (ret)
		return ret;
	ret = snapshot("i2c-tfa9890:00", tfa_regs, ARRAY_SIZE(tfa_regs));
	if (ret)
		return ret;
	return snapshot("i2c-tfa9890:01", tfa_regs, ARRAY_SIZE(tfa_regs));
}

static void __exit mp2_clock_probe_exit(void) { }
module_init(mp2_clock_probe_init);
module_exit(mp2_clock_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary Mi Pad 2 audio register/cache audit");
