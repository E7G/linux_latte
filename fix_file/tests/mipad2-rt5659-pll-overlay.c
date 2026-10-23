// SPDX-License-Identifier: GPL-2.0-only
/* Temporary DAPM graph overlay; no forced I2C/cache/OTP writes. */
#include <linux/device.h>
#include <linux/dmi.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <sound/soc.h>
#define RT5659_GLB_CLK 0x80
#define RT5659_SCLK_SRC_MASK (3 << 14)
#define RT5659_SCLK_SRC_PLL1 (1 << 14)
static int is_sys_clk_from_pll(struct snd_soc_dapm_widget *w,
			 struct snd_soc_dapm_widget *sink)
{
	unsigned int val;
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);

	val = snd_soc_component_read(component, RT5659_GLB_CLK);
	val &= RT5659_SCLK_SRC_MASK;
	if (val == RT5659_SCLK_SRC_PLL1)
		return 1;
	else
		return 0;
}
static const struct snd_soc_dapm_route routes[] = {
	{ "I2S1", NULL, "PLL", is_sys_clk_from_pll },
	{ "I2S2", NULL, "PLL", is_sys_clk_from_pll },
	{ "I2S3", NULL, "PLL", is_sys_clk_from_pll },
};
static int update(bool add)
{
	struct device *dev;
	struct snd_soc_component *component;
	int ret = -ENODEV;
	dev = bus_find_device_by_name(&i2c_bus_type, NULL, "i2c-10EC5659:01");
	if (!dev)
		return -ENODEV;
	device_lock(dev);
	component = snd_soc_lookup_component(dev, NULL);
	if (!component)
		goto out;
	if (add) {
		ret = snd_soc_dapm_add_routes(snd_soc_component_to_dapm(component), routes, ARRAY_SIZE(routes));
		if (ret)
			goto out;
	} else {
		snd_soc_dapm_del_routes(snd_soc_component_to_dapm(component), routes, ARRAY_SIZE(routes));
	}
	ret = snd_soc_dapm_sync(snd_soc_component_to_dapm(component));
	if (ret && add) {
		snd_soc_dapm_del_routes(snd_soc_component_to_dapm(component), routes, ARRAY_SIZE(routes));
		snd_soc_dapm_sync(snd_soc_component_to_dapm(component));
	}
out:
	device_unlock(dev);
	put_device(dev);
	return ret;
}
static int __init mp2_pll_route_init(void)
{
	if (!dmi_match(DMI_PRODUCT_NAME, "Mipad2") || !dmi_match(DMI_SYS_VENDOR, "Xiaomi Inc"))
		return -ENODEV;
	return update(true);
}
static void __exit mp2_pll_route_exit(void) { update(false); }
module_init(mp2_pll_route_init);
module_exit(mp2_pll_route_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary MiPad2 conditional I2S PLL DAPM route overlay");
