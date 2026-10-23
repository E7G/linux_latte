// SPDX-License-Identifier: GPL-2.0-only
/* Temporary DAPM graph overlay; no forced I2C/cache/OTP writes. */
#include <linux/device.h>
#include <linux/dmi.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <sound/soc.h>
static const struct snd_soc_dapm_route routes[] = {
	{"Platform Clock", NULL, "PLL"},
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
		ret = snd_soc_dapm_add_routes(snd_soc_card_to_dapm(component->card), routes, ARRAY_SIZE(routes));
		if (ret)
			goto out;
	} else {
		snd_soc_dapm_del_routes(snd_soc_card_to_dapm(component->card), routes, ARRAY_SIZE(routes));
	}
	ret = snd_soc_dapm_sync(snd_soc_card_to_dapm(component->card));
	if (ret && add) {
		snd_soc_dapm_del_routes(snd_soc_card_to_dapm(component->card), routes, ARRAY_SIZE(routes));
		snd_soc_dapm_sync(snd_soc_card_to_dapm(component->card));
	}
out:
	device_unlock(dev);
	put_device(dev);
	return ret;
}
static int __init mp2_board_pll_init(void)
{
	if (!dmi_match(DMI_PRODUCT_NAME, "Mipad2") || !dmi_match(DMI_SYS_VENDOR, "Xiaomi Inc"))
		return -ENODEV;
	return update(true);
}
static void __exit mp2_board_pll_exit(void) { update(false); }
module_init(mp2_board_pll_init);
module_exit(mp2_board_pll_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Temporary MiPad2 board clock PLL supply dependency");
