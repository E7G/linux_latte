// SPDX-License-Identifier: GPL-2.0-only
/* Actual IIO core APIs with an unregistered in-memory provider, no hardware. */
#include <kunit/test.h>
#include <linux/iio/consumer.h>
#include <linux/iio/driver.h>
#include <linux/iio/iio.h>
#include <linux/iio/machine.h>
#include <linux/module.h>

struct map_fixture {
	struct iio_dev *provider;
	struct iio_channel *channel;
	struct iio_map maps[2];
	bool mapped;
};

static int map_read_raw(struct iio_dev *indio_dev,
		const struct iio_chan_spec *channel, int *val, int *val2, long mask)
{
	if (mask != IIO_CHAN_INFO_PROCESSED)
		return -EINVAL;
	*val = 24950;
	return IIO_VAL_INT;
}

static const struct iio_info map_info = { .read_raw = map_read_raw };
static const struct iio_chan_spec map_channel = {
	.type = IIO_TEMP,
	.datasheet_name = "SYSTEMP0",
	.info_mask_separate = BIT(IIO_CHAN_INFO_PROCESSED),
};

static void map_cleanup(void *context)
{
	struct map_fixture *fixture = context;

	if (!IS_ERR_OR_NULL(fixture->channel))
		iio_channel_release(fixture->channel);
	if (fixture->mapped)
		iio_map_array_unregister(fixture->provider);
	iio_device_free(fixture->provider);
}

static struct map_fixture *map_create(struct kunit *test, const char *label)
{
	struct map_fixture *fixture;
	int ret;

	fixture = kunit_kzalloc(test, sizeof(*fixture), GFP_KERNEL);
	if (!fixture)
		return NULL;
	fixture->provider = iio_device_alloc(NULL, 0);
	if (!fixture->provider)
		return NULL;
	fixture->provider->channels = &map_channel;
	fixture->provider->num_channels = 1;
	fixture->provider->info = &map_info;
	ret = kunit_add_action_or_reset(test, map_cleanup, fixture);
	if (ret)
		return NULL;
	fixture->maps[0] = (struct iio_map)IIO_MAP(label, "chtwc-iio-kunit",
						 "chtwc-iio-kunit-SYS0");
	ret = iio_map_array_register(fixture->provider, fixture->maps);
	if (ret)
		return NULL;
	fixture->mapped = true;
	return fixture;
}

static void iio_map_reference_test(struct kunit *test)
{
	struct map_fixture *fixture = map_create(test, "SYSTEMP0");
	struct iio_channel *missing;
	int val = 0;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	fixture->channel = iio_channel_get(NULL, "chtwc-iio-kunit-SYS0");
	KUNIT_ASSERT_NOT_ERR_OR_NULL(test, fixture->channel);
	KUNIT_EXPECT_PTR_EQ(test, fixture->channel->indio_dev, fixture->provider);
	KUNIT_EXPECT_PTR_EQ(test, fixture->channel->channel, &map_channel);
	KUNIT_ASSERT_EQ(test, iio_map_array_unregister(fixture->provider), 0);
	fixture->mapped = false;
	missing = iio_channel_get(NULL, "chtwc-iio-kunit-SYS0");
	KUNIT_EXPECT_EQ(test, PTR_ERR_OR_ZERO(missing), -ENODEV);
	if (!IS_ERR(missing))
		iio_channel_release(missing);
	KUNIT_EXPECT_EQ(test, iio_read_channel_processed(fixture->channel, &val), 0);
	KUNIT_EXPECT_EQ(test, val, 24950);
}

static void iio_map_invalid_label_test(struct kunit *test)
{
	struct map_fixture *fixture = map_create(test, "unknown-label");

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	fixture->channel = iio_channel_get(NULL, "chtwc-iio-kunit-SYS0");
	KUNIT_EXPECT_TRUE(test, IS_ERR(fixture->channel));
	KUNIT_EXPECT_EQ(test, PTR_ERR(fixture->channel), -EINVAL);
}

static struct kunit_case map_cases[] = {
	KUNIT_CASE(iio_map_reference_test),
	KUNIT_CASE(iio_map_invalid_label_test),
	{}
};

static struct kunit_suite map_suite = {
	.name = "chtwc-iio-map",
	.test_cases = map_cases,
};
kunit_test_suite(map_suite);

MODULE_LICENSE("GPL");
