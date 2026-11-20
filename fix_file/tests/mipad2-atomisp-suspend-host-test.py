#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise actual AtomISP system sleep callbacks with fake PM and CSS."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
device = (Path(sys.argv[1]) if len(sys.argv) == 2 else
          root / "drivers/staging/media/atomisp/pci/atomisp_v4l2.c")
source = device.read_text()
start = source.index("static int atomisp_suspend(struct device *dev)")
end = source.index("int atomisp_csi_lane_config(", start)

mock = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>

struct atomisp_sub_device {
	bool streaming;
	bool stream_prepared;
	bool recreate_streams_on_resume;
};

struct device;
struct atomisp_device {
	struct device *dev;
	int lock;
	struct atomisp_sub_device asd;
};

struct device {
	struct atomisp_device *data;
};

static int wake_error, off_error, on_error, create_error;
static bool awake;
static int event_count;
static int events[4];
enum { WAKE = 1, DESTROY, OFF, ON, CREATE };

static void trace(int id)
{
	assert(event_count < 4);
	events[event_count++] = id;
}

static void grab(int *lock)
{
	assert(!*lock);
	*lock = 1;
}

static void release(int *lock)
{
	assert(*lock == 1);
	*lock = 0;
}

#define spin_lock_irqsave(lock, flags) do { (flags) = 42; grab(lock); } while (0)
#define spin_unlock_irqrestore(lock, flags) do { assert((flags) == 42); release(lock); } while (0)
#define dev_err(...) do { } while (0)

static void *dev_get_drvdata(struct device *dev)
{
	return dev->data;
}

static int pm_runtime_resume(struct device *dev)
{
	assert(!dev->data->lock);
	trace(WAKE);
	awake = wake_error >= 0;
	return wake_error;
}

static void atomisp_destroy_pipes_stream(struct atomisp_sub_device *asd)
{
	assert(awake && "CSS must not be touched after a failed wake");
	assert(asd->recreate_streams_on_resume == asd->stream_prepared);
	trace(DESTROY);
}

static int atomisp_power_off(struct device *dev)
{
	assert(awake && !dev->data->lock);
	trace(OFF);
	if (!off_error)
		awake = false;
	return off_error;
}

static int atomisp_power_on(struct device *dev)
{
	assert(!dev->data->lock);
	trace(ON);
	awake = on_error == 0;
	return on_error;
}

static int atomisp_create_pipes_stream(struct atomisp_sub_device *asd)
{
	assert(awake && asd->recreate_streams_on_resume);
	trace(CREATE);
	return create_error;
}
"""

cases = r"""
int main(void)
{
	const int resume_results[] = { 0, 1, -EIO, -ETIMEDOUT, -EACCES, -EINVAL, -EAGAIN };
	const int off_results[] = { 0, -ENXIO, -EIO, -ETIMEDOUT };
	const int rebuild_results[] = { 0, -ENOMEM, -EIO, -EINVAL };
	unsigned int suspends = 0, resumes = 0;

	for (int streaming = 0; streaming < 2; streaming++)
	for (int prepared = 0; prepared < 2; prepared++)
	for (int old_flag = 0; old_flag < 2; old_flag++)
	for (unsigned int r = 0; r < sizeof(resume_results) / sizeof(resume_results[0]); r++)
	for (unsigned int o = 0; o < sizeof(off_results) / sizeof(off_results[0]); o++) {
		struct atomisp_device isp = { .asd = { streaming, prepared, old_flag } };
		struct device dev = { .data = &isp };
		int ret;

		isp.dev = &dev;
		wake_error = resume_results[r];
		off_error = off_results[o];
		event_count = 0;
		awake = wake_error == 1;
		ret = atomisp_suspend(&dev);
		assert(!isp.lock);
		assert(isp.asd.streaming == !!streaming && isp.asd.stream_prepared == !!prepared);
		if (streaming) {
			assert(ret == -EINVAL && !event_count);
			assert(isp.asd.recreate_streams_on_resume == !!old_flag);
		} else if (wake_error < 0) {
			assert(ret == wake_error && event_count == 1 && events[0] == WAKE);
			assert(isp.asd.recreate_streams_on_resume == !!old_flag);
		} else {
			assert(ret == off_error && event_count == 3);
			assert(events[0] == WAKE && events[1] == DESTROY && events[2] == OFF);
			assert(isp.asd.recreate_streams_on_resume == !!prepared);
		}
		suspends++;
	}

	for (int recreate = 0; recreate < 2; recreate++)
	for (unsigned int p = 0; p < sizeof(off_results) / sizeof(off_results[0]); p++)
	for (unsigned int c = 0; c < sizeof(rebuild_results) / sizeof(rebuild_results[0]); c++) {
		struct atomisp_device isp = { .asd.recreate_streams_on_resume = recreate };
		struct device dev = { .data = &isp };
		bool create;
		int ret;

		isp.dev = &dev;
		on_error = off_results[p];
		create_error = rebuild_results[c];
		create = recreate && !on_error;
		event_count = 0;
		awake = false;
		ret = atomisp_resume(&dev);
		assert(ret == (on_error ? on_error : (create ? create_error : 0)));
		assert(event_count == 1 + create && events[0] == ON);
		if (create)
			assert(events[1] == CREATE);
		resumes++;
	}
	printf("PASS %u AtomISP suspend and %u resume sequences, including unchanged positive wake\n",
	       suspends, resumes);
	return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-atomisp-suspend-") as temp:
    directory = Path(temp)
    unit = directory / "test.c"
    binary = directory / "test"
    unit.write_text(mock + source[start:end] + cases)
    cc = shlex.split(os.environ.get("CC", "gcc"))
    for level in ("-O0", "-O2"):
        subprocess.run(cc + [level, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                             "-fsanitize=undefined", "-fno-sanitize-recover=all",
                             str(unit), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
