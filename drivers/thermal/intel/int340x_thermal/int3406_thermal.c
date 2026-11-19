// SPDX-License-Identifier: GPL-2.0-only
/*
 * INT3406 thermal driver for display participant device
 *
 * Copyright (C) 2016, Intel Corporation
 * Authors: Aaron Lu <aaron.lu@intel.com>
 */

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/acpi.h>
#include <linux/backlight.h>
#include <linux/dmi.h>
#include <linux/string.h>
#include <linux/thermal.h>
#include <acpi/video.h>

#define INT3406_BRIGHTNESS_LIMITS_CHANGED	0x80

struct int3406_thermal_data {
	struct mutex lock;
	int upper_limit;
	int lower_limit;
	bool limit_brightness;
	unsigned long cooling_state;
	acpi_handle handle;
	struct acpi_video_device_brightness *br;
	struct backlight_device *backlight;
	struct thermal_cooling_device *cooling_dev;
};

/*
 * According to the ACPI spec,
 * "Each brightness level is represented by a number between 0 and 100,
 * and can be thought of as a percentage. For example, 50 can be 50%
 * power consumption or 50% brightness, as defined by the OEM."
 *
 * As int3406 device uses this value to communicate with the native
 * graphics driver, we make the assumption that it represents
 * the percentage of brightness only
 */
#define ACPI_TO_RAW(v, d) (d->backlight->props.max_brightness * v / 100)
#define RAW_TO_ACPI(v, d) (v * 100 / d->backlight->props.max_brightness)

static int
int3406_thermal_get_max_state(struct thermal_cooling_device *cooling_dev,
			      unsigned long *state)
{
	struct int3406_thermal_data *d = cooling_dev->devdata;

	guard(mutex)(&d->lock);
	*state = d->upper_limit - d->lower_limit;
	return 0;
}

static int int3406_thermal_apply_state(struct int3406_thermal_data *d,
				       unsigned long state)
{
	int acpi_level, raw_level, ret;

	if (state > d->upper_limit - d->lower_limit)
		return -EINVAL;

	acpi_level = d->br->levels[d->upper_limit - state];

	raw_level = ACPI_TO_RAW(acpi_level, d);

	if (!d->limit_brightness)
		return backlight_device_set_brightness(d->backlight, raw_level);

	ret = backlight_device_set_brightness_limit(d->backlight, raw_level);
	if (!ret)
		d->cooling_state = state;
	return ret;
}

static int
int3406_thermal_set_cur_state(struct thermal_cooling_device *cooling_dev,
				      unsigned long state)
{
	struct int3406_thermal_data *d = cooling_dev->devdata;

	guard(mutex)(&d->lock);
	return int3406_thermal_apply_state(d, state);
}

static int
int3406_thermal_get_cur_state(struct thermal_cooling_device *cooling_dev,
			      unsigned long *state)
{
	struct int3406_thermal_data *d = cooling_dev->devdata;
	int acpi_level;
	int index;

	guard(mutex)(&d->lock);
	if (d->limit_brightness) {
		*state = d->cooling_state;
		return 0;
	}

	acpi_level = RAW_TO_ACPI(d->backlight->props.brightness, d);

	/*
	 * There is no 1:1 mapping between the firmware interface level
	 * with the raw interface level, we will have to find one that is
	 * right above it.
	 */
	for (index = d->lower_limit; index < d->upper_limit; index++) {
		if (acpi_level <= d->br->levels[index])
			break;
	}

	*state = d->upper_limit - index;
	return 0;
}

static const struct thermal_cooling_device_ops video_cooling_ops = {
	.get_max_state = int3406_thermal_get_max_state,
	.get_cur_state = int3406_thermal_get_cur_state,
	.set_cur_state = int3406_thermal_set_cur_state,
};

static int int3406_thermal_get_index(int *array, int nr, int value)
{
	int i;

	for (i = 2; i < nr; i++) {
		if (array[i] == value)
			break;
	}
	return i == nr ? -ENOENT : i;
}

static void int3406_thermal_get_limit(struct int3406_thermal_data *d)
{
	acpi_status status;
	unsigned long long lower_limit, upper_limit;

	status = acpi_evaluate_integer(d->handle, "DDDL", NULL, &lower_limit);
	if (ACPI_SUCCESS(status))
		d->lower_limit = int3406_thermal_get_index(d->br->levels,
					d->br->count, lower_limit);

	status = acpi_evaluate_integer(d->handle, "DDPC", NULL, &upper_limit);
	if (ACPI_SUCCESS(status))
		d->upper_limit = int3406_thermal_get_index(d->br->levels,
					d->br->count, upper_limit);

	/* lower_limit and upper_limit should be always set */
	d->lower_limit = d->lower_limit > 0 ? d->lower_limit : 2;
	d->upper_limit = d->upper_limit > 0 ? d->upper_limit : d->br->count - 1;
}

static int int3406_thermal_refresh_limits(struct int3406_thermal_data *d)
{
	int old_lower = d->lower_limit, old_upper = d->upper_limit;
	unsigned long state;
	int ret = 0;

	int3406_thermal_get_limit(d);
	if (d->upper_limit < d->lower_limit) {
		ret = -EINVAL;
	} else if (d->limit_brightness) {
		state = min_t(unsigned long, d->cooling_state,
			      d->upper_limit - d->lower_limit);
		ret = int3406_thermal_apply_state(d, state);
	}
	if (ret) {
		d->lower_limit = old_lower;
		d->upper_limit = old_upper;
	}
	return ret;
}

static void int3406_notify(acpi_handle handle, u32 event, void *data)
{
	struct int3406_thermal_data *d = data;
	int ret;

	if (event != INT3406_BRIGHTNESS_LIMITS_CHANGED)
		return;

	{
		guard(mutex)(&d->lock);
		ret = int3406_thermal_refresh_limits(d);
	}
	if (!ret)
		thermal_cooling_device_update(d->cooling_dev);
	else
		dev_warn_ratelimited(&d->cooling_dev->device,
				     "Cannot refresh brightness limits: %d\n", ret);
}

static void int3406_thermal_clear_limit(struct int3406_thermal_data *d)
{
	int ret;

	if (!d->limit_brightness)
		return;
	ret = backlight_device_set_brightness_limit(d->backlight,
						    d->backlight->props.max_brightness);
	if (ret)
		dev_warn(&d->backlight->dev, "Cannot clear brightness limit: %d\n", ret);
}

static void int3406_put_backlight(void *data)
{
	put_device(data);
}

static struct backlight_device *int3406_mipad2_backlight(struct device *dev)
{
	struct backlight_device *bd;
	struct device *supplier;
	int ret;

	/* The LP8556 panel backlight is registered as BACKLIGHT_PLATFORM. */
	bd = backlight_device_get_by_name("lcd-backlight");
	if (!bd)
		return ERR_PTR(-EPROBE_DEFER);

	ret = devm_add_action_or_reset(dev, int3406_put_backlight, &bd->dev);
	if (ret)
		return ERR_PTR(ret);

	supplier = bd->dev.parent;
	if (!supplier || !ACPI_COMPANION(supplier) ||
	    !acpi_dev_hid_uid_match(ACPI_COMPANION(supplier), "LP855600", NULL))
		return ERR_PTR(-ENODEV);

	if (!device_link_add(dev, supplier, DL_FLAG_AUTOPROBE_CONSUMER))
		return ERR_PTR(-ENODEV);

	return bd;
}

static int int3406_thermal_probe(struct platform_device *pdev)
{
	struct acpi_device *adev = ACPI_COMPANION(&pdev->dev);
	struct int3406_thermal_data *d;
	struct backlight_device *bd;
	acpi_status status;
	int ret;

	if (!ACPI_HANDLE(&pdev->dev))
		return -ENODEV;

	d = devm_kzalloc(&pdev->dev, sizeof(*d), GFP_KERNEL);
	if (!d)
		return -ENOMEM;
	mutex_init(&d->lock);
	d->handle = ACPI_HANDLE(&pdev->dev);

	d->limit_brightness = dmi_match(DMI_SYS_VENDOR, "Xiaomi Inc") &&
			      dmi_match(DMI_PRODUCT_NAME, "Mipad2") &&
			      !strcmp(acpi_device_bid(adev), "TDSP");
	if (d->limit_brightness)
		bd = int3406_mipad2_backlight(&pdev->dev);
	else
		bd = backlight_device_get_by_type(BACKLIGHT_RAW);
	if (IS_ERR(bd))
		return PTR_ERR(bd);
	if (!bd)
		return -ENODEV;
	d->backlight = bd;

	ret = acpi_video_get_levels(ACPI_COMPANION(&pdev->dev), &d->br, NULL);
	if (ret)
		return ret;

	if (d->br->count <= 2) {
		ret = -EINVAL;
		goto err_free_levels;
	}
	ret = int3406_thermal_refresh_limits(d);
	if (ret)
		goto err_free_levels;

	d->cooling_dev = thermal_cooling_device_register(acpi_device_bid(adev),
							 d, &video_cooling_ops);
	if (IS_ERR(d->cooling_dev)) {
		ret = PTR_ERR(d->cooling_dev);
		goto err_clear_limit;
	}

	status = acpi_install_notify_handler(adev->handle, ACPI_DEVICE_NOTIFY,
					     int3406_notify, d);
	if (ACPI_FAILURE(status)) {
		ret = -ENODEV;
		goto err_cdev;
	}

	platform_set_drvdata(pdev, d);

	return 0;

err_cdev:
	thermal_cooling_device_unregister(d->cooling_dev);
err_clear_limit:
	int3406_thermal_clear_limit(d);
err_free_levels:
	kfree(d->br);
	return ret;
}

static void int3406_thermal_remove(struct platform_device *pdev)
{
	struct int3406_thermal_data *d = platform_get_drvdata(pdev);

	acpi_remove_notify_handler(d->handle, ACPI_DEVICE_NOTIFY, int3406_notify);
	thermal_cooling_device_unregister(d->cooling_dev);
	int3406_thermal_clear_limit(d);
	kfree(d->br);
}

static const struct acpi_device_id int3406_thermal_match[] = {
	{"INT3406", 0},
	{}
};

MODULE_DEVICE_TABLE(acpi, int3406_thermal_match);

static struct platform_driver int3406_thermal_driver = {
	.probe = int3406_thermal_probe,
	.remove = int3406_thermal_remove,
	.driver = {
		   .name = "int3406 thermal",
		   .acpi_match_table = int3406_thermal_match,
		   },
};

module_platform_driver(int3406_thermal_driver);

MODULE_DESCRIPTION("INT3406 Thermal driver");
MODULE_LICENSE("GPL v2");
