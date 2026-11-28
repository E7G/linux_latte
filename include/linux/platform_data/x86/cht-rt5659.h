/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_PLATFORM_DATA_X86_CHT_RT5659_H
#define _LINUX_PLATFORM_DATA_X86_CHT_RT5659_H

#include <linux/acpi.h>
#include <linux/i2c.h>

struct cht_rt5659_lookup {
	acpi_handle handle;
	struct device *codec;
};

static inline int cht_rt5659_match_codec(struct device *dev, void *data)
{
	struct cht_rt5659_lookup *lookup = data;

	if (!i2c_verify_client(dev) ||
	    !acpi_dev_hid_uid_match(ACPI_COMPANION(dev), "10EC5659", NULL) ||
	    (lookup->handle && ACPI_HANDLE(dev) != lookup->handle))
		return 0;

	if (lookup->codec)
		return -ENOTUNIQ;

	lookup->codec = get_device(dev);
	return 0;
}

/* Return the referenced I2C client device, or an error pointer. */
static inline struct device *cht_rt5659_find_codec(bool mipad2)
{
	struct cht_rt5659_lookup lookup = {};
	acpi_handle handle;
	int ret;

	/*
	 * The Mi Pad 2 _STA override exposes this physical codec. Prefer
	 * the namespace path over an enumeration suffix such as :01.
	 */
	if (mipad2 && ACPI_SUCCESS(acpi_get_handle(NULL,
						  "\\_SB_.PCI0.I2C2.RTK3",
						  &handle)))
		lookup.handle = handle;

	ret = bus_for_each_dev(&i2c_bus_type, NULL, &lookup,
			       cht_rt5659_match_codec);
	if (ret) {
		put_device(lookup.codec);
		return ERR_PTR(ret);
	}

	if (!lookup.codec)
		return ERR_PTR(-EPROBE_DEFER);

	return lookup.codec;
}

#endif
