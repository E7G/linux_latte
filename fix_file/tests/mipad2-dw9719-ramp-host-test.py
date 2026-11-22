#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the actual DW9719-family PM callbacks with a fake lens transport."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


MOCK = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#define DW9719_CTRL_STEPS 16
#define DW9719_CTRL_DELAY_US 1000
#define DW9719_MAX_FOCUS_POS 1023
#define max(a, b) ((a) > (b) ? (a) : (b))
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))

struct v4l2_ctrl { int val; };
struct dw9719_device { struct { struct v4l2_ctrl *focus; } ctrls; };
struct v4l2_subdev { struct dw9719_device *lens; };
struct device { struct v4l2_subdev *subdev; };

static struct {
    int values[66];
    unsigned int writes, waits, ups, downs;
    unsigned int fail_write;
    int up_result, down_result;
} bus;
static struct v4l2_ctrl focus;
static struct dw9719_device lens = { .ctrls.focus = &focus };
static struct v4l2_subdev subdev = { .lens = &lens };
static struct device dev = { .subdev = &subdev };

static struct v4l2_subdev *dev_get_drvdata(struct device *d)
{
    return d->subdev;
}

static struct dw9719_device *to_dw9719_device(struct v4l2_subdev *sd)
{
    return sd->lens;
}

static int dw9719_power_up(struct dw9719_device *d, bool probe)
{
    assert(d == &lens && !probe);
    assert(!bus.writes && !bus.waits && !bus.downs && !bus.ups);
    bus.ups++;
    return bus.up_result;
}

static int dw9719_power_down(struct dw9719_device *d)
{
    assert(d == &lens && !bus.downs);
    bus.downs++;
    return bus.down_result;
}

static int dw9719_t_focus_abs(struct dw9719_device *d, int value)
{
    assert(d == &lens && !bus.downs);
    assert(value >= 0 && value <= DW9719_MAX_FOCUS_POS);
    assert(bus.writes < ARRAY_SIZE(bus.values) && bus.waits == bus.writes);
    bus.values[bus.writes++] = value;
    if (bus.writes == bus.fail_write)
        return -EREMOTEIO;
    return 0;
}

static void usleep_range(unsigned int min_us, unsigned int max_us)
{
    assert(min_us == 1000 && max_us == 1010);
    assert(bus.waits + 1 == bus.writes && !bus.downs);
    bus.waits++;
}
"""

CHECK = r"""
static void expect_trace(int target, unsigned int count, bool resume,
                         unsigned int failed_write)
{
    for (unsigned int i = 0; i < count; i++) {
        int expected;
        if (resume)
            expected = target - (target / 16 - (int)i) * 16;
        else
            expected = i <= (unsigned int)(target / 16) ? target - 16 * (int)i : 0;
        assert(bus.values[i] == expected);
    }
    assert(focus.val == target);
    assert(bus.writes == count && bus.waits == count - !!failed_write);
    assert(bus.ups == resume);
    assert(bus.downs == (resume ? !!failed_write : !failed_write));
}

int main(void)
{
    unsigned int faults = 0;

    for (int target = 0; target <= DW9719_MAX_FOCUS_POS; target++) {
        unsigned int rise = target / 16 + 1;
        unsigned int fall = rise + !!(target % 16);
        focus.val = target;

        memset(&bus, 0, sizeof(bus));
        assert(!dw9719_resume(&dev));
        expect_trace(target, rise, true, 0);
        assert(bus.values[rise - 1] == target);

        memset(&bus, 0, sizeof(bus));
        assert(!dw9719_suspend(&dev));
        expect_trace(target, fall, false, 0);
        assert(!bus.values[fall - 1]);

        memset(&bus, 0, sizeof(bus));
        bus.up_result = -ENXIO;
        assert(dw9719_resume(&dev) == -ENXIO);
        assert(bus.ups == 1 && !bus.writes && !bus.waits && !bus.downs);

        memset(&bus, 0, sizeof(bus));
        bus.down_result = -EAGAIN;
        assert(dw9719_suspend(&dev) == -EAGAIN);
        expect_trace(target, fall, false, 0);

        for (unsigned int at = 1; at <= rise; at++) {
            memset(&bus, 0, sizeof(bus));
            bus.fail_write = at;
            bus.down_result = -EAGAIN;
            assert(dw9719_resume(&dev) == -EREMOTEIO);
            expect_trace(target, at, true, at);
            faults++;
        }

        for (unsigned int at = 1; at <= fall; at++) {
            memset(&bus, 0, sizeof(bus));
            bus.fail_write = at;
            assert(dw9719_suspend(&dev) == -EREMOTEIO);
            expect_trace(target, at, false, at);
            faults++;
        }
    }

    printf("PASS: 1024 focus positions, both endpoints, %u injected write failures\n",
           faults);
    return 0;
}
"""


def main():
    if len(sys.argv) > 2:
        raise SystemExit(f"Usage: {sys.argv[0]} [path/to/dw9719.c]")
    source_path = (Path(sys.argv[1]) if len(sys.argv) == 2 else
                   Path(__file__).resolve().parents[2] / "drivers/media/i2c/dw9719.c")
    source = source_path.read_text()
    start = source.index("static int dw9719_suspend(")
    end = source.index("static int dw9719_open(", start)
    implementation = source[start:end]
    with tempfile.TemporaryDirectory(prefix="mipad2-dw9719-ramp-") as temp:
        fixture = Path(temp) / "probe.c"
        binary = Path(temp) / "probe"
        fixture.write_text(MOCK + implementation + CHECK)
        cc = shlex.split(os.environ.get("CC", "cc"))
        subprocess.run(cc + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                             str(fixture), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
