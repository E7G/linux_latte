/* SPDX-License-Identifier: GPL-2.0-only */
/* Actual lookup body, modeled unregister exactly when its guard unlocks. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct iio_chan_spec { int id; };
struct iio_dev { unsigned int refs; struct iio_chan_spec spec; };
struct iio_map { const char *consumer_dev_name, *consumer_channel, *adc_channel_label; };
struct iio_map_internal { const struct iio_map *map; struct iio_dev *indio_dev; };
struct iio_channel { struct iio_dev *indio_dev; const struct iio_chan_spec *channel; };
static struct iio_dev provider;
static struct iio_map map;
static struct iio_map_internal *node;
static int iio_map_list, iio_map_list_lock, fail_alloc, allocations, unregister_on_unlock;
static unsigned int checks;
#define GFP_KERNEL 0
#define ERR_PTR(error) ((void *)(intptr_t)(error))
#define list_for_each_entry(pos, list, member) \
	for ((void)(list), (pos)=node; (pos); (pos)=NULL)

struct mock_guard { int *mutex; int active; };
static struct mock_guard mock_lock(int *mutex)
{
	assert(!*mutex); *mutex=1;
	return (struct mock_guard){mutex,1};
}
static void mock_unlock(struct mock_guard *guard)
{
	assert(*guard->mutex); *guard->mutex=0;
	if (unregister_on_unlock) { free(node); node=NULL; }
}
#define guard(kind) struct mock_guard function_guard __attribute__((cleanup(mock_unlock))) = mock_lock
#define scoped_guard(kind, lock) \
	for (struct mock_guard scope __attribute__((cleanup(mock_unlock))) = mock_lock(lock); \
	     scope.active; scope.active=0)
static void free_channel(struct iio_channel **channel) { free(*channel); }
#define __free(kind) __attribute__((cleanup(free_channel)))
#define return_ptr(ptr) do { __auto_type result=(ptr); (ptr)=NULL; return result; } while (0)
static void *kzalloc(size_t size, int flags)
{
	(void)flags; allocations++;
	return fail_alloc ? NULL : calloc(1,size);
}
static void iio_device_get(struct iio_dev *device) { device->refs++; }
static void iio_device_put(struct iio_dev *device) { assert(device->refs>1); device->refs--; }
static const struct iio_chan_spec *iio_chan_spec_from_name(struct iio_dev *device, const char *name)
{
	assert(iio_map_list_lock);
	return !strcmp(name,"SYSTEMP0") ? &device->spec : NULL;
}

#include "actual-iio-map-get.c"

static void setup(const char *label)
{
	provider=(struct iio_dev){.refs=1};
	map=(struct iio_map){"cht_wcove_thermal","SYS0",label};
	node=malloc(sizeof(*node)); assert(node);
	*node=(struct iio_map_internal){&map,&provider};
	iio_map_list_lock=0; fail_alloc=0; allocations=0; unregister_on_unlock=1;
}

int main(void)
{
	struct iio_channel *channel;
	const char *names[]={"cht_wcove_thermal",NULL,"cht_wcove_thermal"};
	const char *channels[]={"SYS0","SYS0",NULL};
	unsigned int i;

	for (i=0;i<3;i++) {
		setup("SYSTEMP0");
		channel=iio_channel_get_sys(names[i],channels[i]);
		assert((intptr_t)channel>0 && channel->indio_dev==&provider);
		assert(channel->channel==&provider.spec && provider.refs==2);
		assert(!node && !iio_map_list_lock);
		iio_device_put(channel->indio_dev); free(channel); checks++;
	}
	setup("SYSTEMP0"); fail_alloc=1;
	assert(iio_channel_get_sys("cht_wcove_thermal","SYS0")==ERR_PTR(-ENOMEM));
	assert(provider.refs==1 && !node && !iio_map_list_lock); checks++;
	setup("bad-label");
	assert(iio_channel_get_sys("cht_wcove_thermal","SYS0")==ERR_PTR(-EINVAL));
	assert(provider.refs==1 && !node && !iio_map_list_lock); checks++;
	setup("SYSTEMP0"); fail_alloc=1;
	assert(iio_channel_get_sys("other","SYS0")==ERR_PTR(-ENODEV));
	assert(!allocations && provider.refs==1 && !node && !iio_map_list_lock); checks++;
	setup(NULL);
	channel=iio_channel_get_sys(NULL,"SYS0");
	assert((intptr_t)channel>0 && !channel->channel && provider.refs==2);
	iio_device_put(channel->indio_dev); free(channel); checks++;
	setup("SYSTEMP0");
	assert(iio_channel_get_sys(NULL,NULL)==ERR_PTR(-ENODEV));
	assert(node && !allocations && provider.refs==1); free(node); node=NULL; checks++;
	printf("PASS %u actual IIO map lookup/lifetime/error cases\n",checks);
	return 0;
}
