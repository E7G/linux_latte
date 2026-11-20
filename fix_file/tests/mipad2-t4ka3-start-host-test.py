#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the actual T4KA3 start/unwind with a modeled sensor and runtime PM."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

root = Path(os.environ.get("MIPAD2_KERNEL_SOURCE",
                           Path(__file__).resolve().parents[2]))
source = (root / "drivers/media/i2c/t4ka3.c").read_text()
match = re.search(r"^static int t4ka3_release_group_hold\([^;{}]*\)\s*\{",
                  source, re.M)
end = source.index("static int t4ka3_disable_stream(")
if not match or match.start() >= end:
    raise SystemExit("T4KA3 start/recovery callbacks not found")
callbacks = source[match.start():end]

mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
struct v4l2_subdev { void *dev, *owner; };
struct v4l2_subdev_state { int unused; };
struct t4ka3_data {
	struct v4l2_subdev sd;
	void *dev, *regmap;
	struct { int handler; } ctrls;
	bool group_hold_pending;
	int streaming;
};

enum action { STANDBY, RELEASE, INIT, HOLD, PRE, MODE, POST, CTRL, ON };
static const int t4ka3_init_config[] = { INIT }, t4ka3_pre_mode_set_regs[] = { PRE },
	t4ka3_post_mode_set_regs[] = { POST };
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define T4KA3_REG_STREAM 0x100
#define T4KA3_REG_PARAM_HOLD 0x104
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)

static enum action expected[10], seen[12];
static unsigned int expected_count, count, fail_at, cleanup_faults;
static int refs, normal_puts, sync_puts, resume_result, main_errno;
static bool streaming, group_hold, fault_took_effect, landed;

static struct t4ka3_data *to_t4ka3_sensor(struct v4l2_subdev *sd)
{
	return sd->owner;
}

static int pm_runtime_resume_and_get(void *dev)
{
	(void)dev;
	if (!resume_result)
		refs++;
	return resume_result;
}

static void pm_runtime_put(void *dev)
{
	(void)dev;
	assert(refs > 0);
	refs--;
	normal_puts++;
	/* No implicit hardware reset: an ordinary put can be asynchronous. */
}

static int pm_runtime_put_sync_suspend(void *dev)
{
	(void)dev;
	assert(refs > 0);
	sync_puts++;
	if (--refs)
		return -EBUSY;
	group_hold = streaming = false;
	return 0;
}

static int act(enum action a, int *err)
{
	int ret = 0;

	if (err && *err)
		return *err;
	assert(count < ARRAY_SIZE(seen));
	seen[count++] = a;
	landed = true;
	if (!fail_at || count <= fail_at) {
		assert(count <= expected_count && a == expected[count - 1]);
		if (count == fail_at) {
			landed = fault_took_effect;
			ret = main_errno;
		}
	} else if (count == fail_at + 1) {
		assert(a == STANDBY);
		if (cleanup_faults & 1) {
			landed = false;
			ret = -EREMOTEIO;
		}
	} else {
		assert(count == fail_at + 2 && !(cleanup_faults & 1) && a == RELEASE);
		if (cleanup_faults & 2) {
			landed = false;
			ret = -ETIMEDOUT;
		}
	}
	if (err && ret)
		*err = ret;
	return ret;
}

static int cci_write(void *map, int reg, int value, int *err)
{
	enum action a;
	int ret;

	(void)map;
	if (err && *err)
		return *err;
	assert(value == 0 || value == 1);
	assert(reg == T4KA3_REG_STREAM || reg == T4KA3_REG_PARAM_HOLD);
	a = reg == T4KA3_REG_STREAM ? (value ? ON : STANDBY) : (value ? HOLD : RELEASE);
	ret = act(a, err);
	if (landed) {
		if (a == RELEASE || a == HOLD) {
			assert(!streaming);
			group_hold = value;
		} else {
			if (a == ON)
				assert(!group_hold);
			streaming = value;
		}
	}
	return ret;
}

static int config_step(enum action a, int *err)
{
	if (err && *err)
		return *err;
	assert(!streaming && group_hold == (a != INIT));
	return act(a, err);
}

static int cci_multi_reg_write(void *map, const int *data, unsigned int n, int *err)
{
	(void)map;
	assert(n == 1);
	return config_step(*data, err);
}

static int t4ka3_set_mode(struct t4ka3_data *sensor, struct v4l2_subdev_state *state)
{
	(void)sensor;
	(void)state;
	return config_step(MODE, NULL);
}

static int __v4l2_ctrl_handler_setup(int *handler)
{
	(void)handler;
	return config_step(CTRL, NULL);
}
'''

cases = r'''
static void plan(bool stale)
{
	const enum action setup[] = { INIT, HOLD, PRE, MODE, POST, CTRL, RELEASE, ON };

	count = normal_puts = sync_puts = 0;
	expected_count = 0;
	expected[expected_count++] = STANDBY;
	if (stale)
		expected[expected_count++] = RELEASE;
	memcpy(expected + expected_count, setup, sizeof(setup));
	expected_count += ARRAY_SIZE(setup);
}

static void check_start_ok(struct t4ka3_data *t, int extra)
{
	assert(t4ka3_enable_stream(&t->sd, NULL, 0, 1) == 0);
	assert(count == expected_count && !normal_puts && !sync_puts);
	assert(t->streaming && streaming && !group_hold && !t->group_hold_pending);
	assert(refs == extra + 1);
}

static void run_case(int extra, bool stale, unsigned int fail, unsigned int cleanup,
		     bool landed_on_error, int err)
{
	struct t4ka3_data t = { .group_hold_pending = stale };
	bool group_at_failure, release_attempted, recovery_failed;
	enum action failed;

	t.sd.owner = &t;
	refs = extra;
	streaming = false;
	group_hold = stale;
	resume_result = 0;
	fail_at = fail;
	cleanup_faults = cleanup;
	fault_took_effect = landed_on_error;
	main_errno = err;
	plan(stale);
	if (!fail) {
		check_start_ok(&t, extra);
		return;
	}

	assert(t4ka3_enable_stream(&t.sd, NULL, 0, 1) == err && refs == extra);
	assert(!t.streaming);
	failed = expected[fail - 1];
	group_at_failure = (stale && failed == STANDBY) ||
			   (failed >= HOLD && failed <= CTRL) || failed == RELEASE;
	release_attempted = !(cleanup & 1) && group_at_failure;
	recovery_failed = (cleanup & 1) || (release_attempted && (cleanup & 2));
	assert(count == fail + 1 + release_attempted);
	assert(seen[fail] == STANDBY);
	if (release_attempted)
		assert(seen[fail + 1] == RELEASE);
	assert(normal_puts == !recovery_failed && sync_puts == recovery_failed);
	assert(t.group_hold_pending == (group_at_failure && recovery_failed));
	if (!recovery_failed || !extra)
		assert(!streaming && !group_hold);

	/* A second real start must recover, even if another PM user held power. */
	plan(t.group_hold_pending);
	fail_at = 0;
	check_start_ok(&t, extra);
}

int main(void)
{
	const int errors[] = { -EIO, -EREMOTEIO, -ETIMEDOUT, -ENXIO };
	unsigned int n = 0;

	for (int extra = 0; extra <= 1; extra++) {
		for (unsigned int e = 0; e < ARRAY_SIZE(errors); e++) {
			struct t4ka3_data t = { 0 };

			t.sd.owner = &t;
			refs = extra;
			resume_result = errors[e];
			plan(false);
			assert(t4ka3_enable_stream(&t.sd, NULL, 0, 1) == errors[e]);
			assert(!count && !normal_puts && !sync_puts && !t.streaming && refs == extra);
			n++;
		}
		for (int stale = 0; stale <= 1; stale++)
			for (unsigned int fail = 0; fail <= 9U + stale; fail++)
				for (unsigned int cleanup = 0; cleanup < 4; cleanup++)
					for (int effect = 0; effect <= 1; effect++)
						for (unsigned int e = 0; e < ARRAY_SIZE(errors); e++) {
							run_case(extra, stale, fail, cleanup, effect, errors[e]);
							n++;
						}
	}
	printf("PASS %u T4KA3 start/fault/unwind cases with PM and warm recovery\n", n);
}
'''

with tempfile.TemporaryDirectory(prefix="mipad2-t4ka3-start-") as temp:
    directory = Path(temp)
    unit = directory / "test.c"
    binary = directory / "test"
    unit.write_text(mock + callbacks + cases)
    cc = shlex.split(os.environ.get("CC", "gcc"))
    for level in ("-O0", "-O2"):
        subprocess.run(cc + [level, "-g", "-Wall", "-Wextra", "-Werror",
                             "-Wno-unused-parameter", "-fsanitize=undefined",
                             "-fno-sanitize-recover=all", str(unit), "-o",
                             str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
