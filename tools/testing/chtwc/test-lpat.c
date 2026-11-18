/* SPDX-License-Identifier: GPL-2.0-only */
/* The included conversion header and extracted loader/read_raw are real code. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define chtwc_adc_acquire chtwc_real_adc_acquire
#include "intel-chtwc-adc-lpat.h"
#undef chtwc_adc_acquire
#include "lpat-fixture.h"

static unsigned int checks;
#define CHECK(x) do { checks++; assert(x); } while (0)

typedef void *acpi_handle;
typedef unsigned int acpi_object_type;
typedef int acpi_status;
#define ACPI_TYPE_INTEGER 1
#define ACPI_TYPE_PACKAGE 4
#define ACPI_TYPE_METHOD 8
#define ACPI_ALLOCATE_BUFFER ((size_t)-1)
#define ACPI_FAILURE(x) ((x) != 0)
#define GFP_KERNEL 0
struct device { struct device *parent; };
struct acpi_buffer { size_t length; void *pointer; };
union acpi_object {
	unsigned int type;
	struct { unsigned int type; uint64_t value; } integer;
	struct { unsigned int type, count; union acpi_object *elements; } package;
};
struct mutex { int held; };
struct chtwc_adc {
	struct device *dev;
	struct chtwc_adc_lpat_point *lpat;
	unsigned int lpat_count;
	struct mutex lock;
	struct chtwc_adc_io io;
	bool removing, suspended, faulted;
};
struct iio_dev { struct chtwc_adc *adc; };
struct iio_chan_spec { int type; unsigned int channel; };
#define IIO_TEMP 1
#define IIO_RESISTANCE 2
#define IIO_VOLTAGE 3
#define IIO_CHAN_INFO_RAW 0
#define IIO_CHAN_INFO_PROCESSED 1
#define IIO_VAL_INT 1
#define iio_priv(dev) ((dev)->adc)

static union acpi_object objects[2 * CHTWC_LPAT_MAX_POINTS + 2], package;
static unsigned int object_type, evaluates, allocated, released, buffer_released;
static int get_handle_error, get_type_error, evaluate_error, alloc_error;
static int acquired, acquisition_error;
static struct chtwc_adc_sample next_sample;
#define ACPI_HANDLE(dev) ((acpi_handle)(dev))
static acpi_status acpi_get_handle(acpi_handle parent, const char *name, acpi_handle *out)
{
	CHECK(parent && !strcmp(name, "LPAT"));
	*out = parent;
	return get_handle_error;
}
static acpi_status acpi_get_type(acpi_handle handle, acpi_object_type *out)
{
	CHECK(handle);
	*out = object_type;
	return get_type_error;
}
static acpi_status acpi_evaluate_object(acpi_handle handle, const char *name,
				      void *arguments, struct acpi_buffer *buffer)
{
	CHECK(handle && !name && !arguments && buffer->length == ACPI_ALLOCATE_BUFFER);
	evaluates++;
	buffer->pointer = &package;
	return evaluate_error;
}
static void *devm_kcalloc(struct device *dev, size_t count, size_t size, int flags)
{
	CHECK(dev && !flags);
	if (alloc_error)
		return NULL;
	allocated++;
	return calloc(count, size);
}
static void devm_kfree(struct device *dev, void *p)
{
	CHECK(dev && p);
	released++;
	free(p);
}
#define ACPI_FREE(p) do { if (p) buffer_released++; } while (0)
static void mutex_lock(struct mutex *lock) { CHECK(!lock->held); lock->held = 1; }
static void mutex_unlock(struct mutex *lock) { CHECK(lock->held); lock->held = 0; }
static int chtwc_adc_acquire(const struct chtwc_adc_io *io, unsigned int index,
			     struct chtwc_adc_sample *sample)
{
	CHECK(io && index < 11);
	acquired++;
	*sample = next_sample;
	return acquisition_error;
}
#include "actual-lpat-loader.c"
#include "actual-read-raw.c"

static void reset(struct chtwc_adc *adc)
{
	static struct device parent, child = { .parent = &parent };
	unsigned int i;

	memset(adc, 0, sizeof(*adc));
	adc->dev = &child;
	object_type = ACPI_TYPE_PACKAGE;
	get_handle_error = get_type_error = evaluate_error = alloc_error = 0;
	evaluates = allocated = released = buffer_released = 0;
	memset(objects, 0, sizeof(objects));
	for (i = 0; i < ARRAY_SIZE(factory); i++) {
		objects[2 * i].integer.type = ACPI_TYPE_INTEGER;
		objects[2 * i].integer.value = factory[i].decikelvin;
		objects[2 * i + 1].integer.type = ACPI_TYPE_INTEGER;
		objects[2 * i + 1].integer.value = factory[i].ohms;
	}
	package.package.type = ACPI_TYPE_PACKAGE;
	package.package.count = 2 * ARRAY_SIZE(factory);
	package.package.elements = objects;
}

static void loader_tests(void)
{
	struct device orphan = {0};
	struct chtwc_adc adc;
	unsigned int i;
	int ret;

	reset(&adc);
	CHECK(!chtwc_adc_load_lpat(&adc));
	CHECK(adc.lpat_count == ARRAY_SIZE(factory) && evaluates == 1 && allocated == 1);
	CHECK(!memcmp(adc.lpat, factory, sizeof(factory)) && buffer_released == 1);
	devm_kfree(adc.dev, adc.lpat);
	for (i = 0; i < 16; i++) {
		reset(&adc);
		switch (i) {
		case 0: adc.dev = &orphan; break;
		case 1: get_handle_error = 1; break;
		case 2: get_type_error = 1; break;
		case 3: object_type = ACPI_TYPE_METHOD; break;
		case 4: evaluate_error = 1; break;
		case 5: package.type = ACPI_TYPE_INTEGER; break;
		case 6: package.package.count = 3; break;
		case 7: package.package.count = 5; break;
		case 8: package.package.count = 2 * CHTWC_LPAT_MAX_POINTS + 2; break;
		case 9: package.package.elements = NULL; break;
		case 10: objects[0].type = ACPI_TYPE_PACKAGE; break;
		case 11: objects[0].integer.value = UINT64_MAX; break;
		case 12: objects[1].integer.value = (UINT64_C(1) << 32) + 483954; break;
		case 13: objects[3].integer.value = objects[1].integer.value; break;
		case 14: objects[2].integer.value = objects[0].integer.value; break;
		case 15: objects[1].integer.value = 0; break;
		}
		ret = chtwc_adc_load_lpat(&adc);
		if (ret || adc.lpat || adc.lpat_count)
			fprintf(stderr, "loader case %u: status %d, points %u\n",
				i, ret, adc.lpat_count);
		CHECK(!ret && !adc.lpat && !adc.lpat_count);
		CHECK(allocated == released);
		if (i < 4)
			CHECK(!evaluates);
	}
	reset(&adc);
	alloc_error = 1;
	CHECK(chtwc_adc_load_lpat(&adc) == -ENOMEM && !adc.lpat);
	CHECK(buffer_released == 1);
}

static void conversion_tests(void)
{
	struct chtwc_adc_lpat_point copy[ARRAY_SIZE(factory)];
	struct chtwc_adc_sample sample;
	unsigned int index, selector, count, i;
	int actual, expected, ohms, ret;

	CHECK(chtwc_adc_lpat_valid(factory, ARRAY_SIZE(factory)));
	CHECK(!chtwc_adc_lpat_valid(NULL, 30));
	CHECK(!chtwc_adc_lpat_valid(factory, 1));
	CHECK(!chtwc_adc_lpat_valid(factory, CHTWC_LPAT_MAX_POINTS + 1));
	memcpy(copy, factory, sizeof(copy));
	copy[1].ohms = copy[0].ohms;
	CHECK(!chtwc_adc_lpat_valid(copy, ARRAY_SIZE(copy)));
	copy[1] = factory[1]; copy[0].decikelvin = -1;
	CHECK(!chtwc_adc_lpat_valid(copy, ARRAY_SIZE(copy)));
	copy[0].decikelvin = INT_MAX;
	CHECK(!chtwc_adc_lpat_valid(copy, ARRAY_SIZE(copy)));
	for (index = 5; index <= 7; index++) {
		for (selector = 0; selector < 16; selector++) {
			for (count = 0; count <= 4096; count++) {
				sample = (struct chtwc_adc_sample){count, selector};
				actual = 987654321;
				ret = chtwc_adc_temperature(index, &sample, factory,
							    ARRAY_SIZE(factory), &actual);
				if (!count || count == 4095) {
					CHECK(ret == -ENODATA);
				} else if (count > 4095) {
					CHECK(ret == -ERANGE);
				} else if (!selector || selector == 9 || selector >= 12) {
					CHECK(ret == -ENODATA);
				} else {
					CHECK(!chtwc_adc_resistance(index, &sample, &ohms));
					if (ohms > factory[0].ohms || ohms < factory[29].ohms) {
						CHECK(ret == -ERANGE);
					} else {
						for (i = 1; ohms < factory[i].ohms; i++)
							;
						/* Independent weighted-endpoint, long-double oracle. */
						expected = (int)((((long double)factory[i].ohms - ohms) *
							factory[i - 1].decikelvin +
							((long double)ohms - factory[i - 1].ohms) *
							factory[i].decikelvin) * 100 /
							(factory[i].ohms - factory[i - 1].ohms) + 0.0000001L);
						CHECK(!ret && actual == expected - 273150);
					}
				}
				if (ret)
					CHECK(actual == 987654321);
			}
		}
	}
	/* Extreme valid values exercise signed-wide interpolation under UBSan. */
	copy[0] = (struct chtwc_adc_lpat_point){0, INT_MAX};
	copy[1] = (struct chtwc_adc_lpat_point){INT_MAX / 100, 1};
	sample = (struct chtwc_adc_sample){2000, 1};
	CHECK(!chtwc_adc_temperature(5, &sample, copy, 2, &actual));
	CHECK(actual > 0);
	for (index = 0; index < 11; index++) {
		if (index >= 5 && index <= 7)
			continue;
		CHECK(chtwc_adc_temperature(index, &sample, factory, 30, &actual) == -EOPNOTSUPP);
	}
}

static void read_raw_tests(void)
{
	struct chtwc_adc adc;
	struct iio_dev dev = { .adc = &adc };
	struct iio_chan_spec ch = { .type = IIO_TEMP, .channel = 5 };
	int value = 123456, unused = 0, ret, expected;
	unsigned int i;

	reset(&adc);
	CHECK(!chtwc_adc_load_lpat(&adc));
	next_sample = (struct chtwc_adc_sample){2000, 5};
	CHECK(!chtwc_adc_temperature(5, &next_sample, factory, 30, &expected));
	acquired = acquisition_error = 0;
	CHECK(chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_PROCESSED) == IIO_VAL_INT);
	CHECK(acquired == 1 && value == expected && !adc.lock.held);
	for (i = 0; i < 3; i++) {
		adc.removing = i == 0; adc.suspended = i == 1; adc.faulted = i == 2;
		value = 123456; acquired = 0;
		ret = chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_PROCESSED);
		CHECK(ret == (i == 0 ? -ENODEV : i == 1 ? -EBUSY : -EIO));
		CHECK(!acquired && value == 123456 && !adc.lock.held);
	}
	adc.removing = adc.suspended = adc.faulted = false;
	for (i = 0; i < 11; i++) {
		ch.channel = i; value = 123456; acquired = 0;
		ret = chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_PROCESSED);
		CHECK(ret == (i >= 5 && i <= 7 ? IIO_VAL_INT : -EINVAL));
		CHECK(acquired == (i >= 5 && i <= 7));
	}
	ch.channel = 5;
	acquisition_error = -ETIMEDOUT; value = 123456; acquired = 0;
	CHECK(chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_PROCESSED) == -ETIMEDOUT);
	CHECK(acquired == 1 && value == 123456 && !adc.lock.held);
	acquisition_error = 0;
	ch.type = IIO_RESISTANCE;
	CHECK(chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_PROCESSED) == IIO_VAL_INT);
	CHECK(!chtwc_adc_resistance(5, &next_sample, &expected) && value == expected);
	ch.type = IIO_TEMP;
	CHECK(chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_RAW) == IIO_VAL_INT);
	CHECK(value == next_sample.count);
	devm_kfree(adc.dev, adc.lpat); adc.lpat = NULL; acquired = 0;
	CHECK(chtwc_adc_read_raw(&dev, &ch, &value, &unused, IIO_CHAN_INFO_PROCESSED) == -EINVAL);
	CHECK(!acquired);
}

int main(void)
{
	loader_tests();
	conversion_tests();
	read_raw_tests();
	printf("PASS %u checks; actual LPAT loader/read_raw + conversion\n", checks);
	return 0;
}
