#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the RT5659 ACPI match and owned board property teardown."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[2] /
          "drivers/platform/x86/x86-android-tablets/other.c").read_text()
functions = []
for name in ("match_rt5659_client", "xiaomi_mipad2_remove_rt5659_node",
             "xiaomi_mipad2_init_rt5659"):
    matches = re.findall(rf"^static [^\n]+ {name}\([^{{}};]*?^\{{\n.*?^\}}",
                         source, re.M | re.S)
    if len(matches) != 1:
        raise SystemExit(f"expected one production function: {name}")
    functions.extend(matches)

mocks = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#define __init

struct software_node { const char *name; };
struct fwnode_handle { struct fwnode_handle *secondary; const struct software_node *node; };
struct acpi_device { const char *hid; };
struct device {
    bool i2c, registered, locked;
    unsigned int refs;
    struct acpi_device *acpi;
    struct fwnode_handle *fwnode;
};

static const struct software_node rt5659_swnode = { "rt5659" };
static struct fwnode_handle secondary = { .node = &rt5659_swnode };
static struct fwnode_handle foreign, primary, absent;
static struct acpi_device realtek = { "10EC5659" }, lookalike = { "10EC56590" };
static struct device codec, board;
static const int i2c_bus_type;
static bool hide_codec;
static unsigned int added, removed, warnings;
static int add_error, devm_error;
static void (*action)(void *);
static void *action_data;

#define ACPI_COMPANION(dev) ((dev)->acpi)
#define IS_ERR_OR_NULL(node) (!(node) || (node) == &absent)
#define dev_warn(dev, ...) (assert((dev) == &board), warnings++)

static bool i2c_verify_client(struct device *dev)
{
    return dev->i2c;
}

static bool acpi_dev_hid_uid_match(struct acpi_device *acpi, const char *hid, const char *uid)
{
    assert(!uid);
    return acpi && !strcmp(acpi->hid, hid);
}

static struct device *bus_find_device(const int *bus, const void *start,
                                      const void *data,
                                      int (*match)(struct device *, const void *))
{
    assert(bus == &i2c_bus_type && !start && !data);
    if (hide_codec || !match(&codec, data))
        return NULL;
    codec.refs++;
    return &codec;
}

static void put_device(struct device *dev)
{
    assert(dev == &codec && dev->refs && !dev->locked);
    dev->refs--;
}

static void device_lock(struct device *dev)
{
    assert(dev == &codec && !dev->locked && dev->refs);
    dev->locked = true;
}

static void device_unlock(struct device *dev)
{
    assert(dev == &codec && dev->locked);
    dev->locked = false;
}

static struct fwnode_handle *dev_fwnode(struct device *dev)
{
    assert(dev == &codec && dev->locked);
    return dev->fwnode;
}

static bool device_is_registered(struct device *dev)
{
    assert(dev->locked);
    return dev->registered;
}

static const struct software_node *to_software_node(const struct fwnode_handle *node)
{
    return IS_ERR_OR_NULL(node) ? NULL : node->node;
}

static int device_add_software_node(struct device *dev, const struct software_node *node)
{
    assert(dev->locked && dev->refs && dev->fwnode == &primary);
    assert(IS_ERR_OR_NULL(primary.secondary) && node == &rt5659_swnode);
    if (add_error)
        return add_error;
    primary.secondary = &secondary;
    added++;
    return 0;
}

static void device_remove_software_node(struct device *dev)
{
    assert(dev->locked && primary.secondary == &secondary);
    primary.secondary = NULL;
    removed++;
}

static int devm_add_action_or_reset(struct device *dev, void (*fn)(void *), void *data)
{
    assert(dev == &board && data == &codec && !codec.locked && !action);
    if (devm_error)
        fn(data);
    else {
        action = fn;
        action_data = data;
    }
    return devm_error;
}
"""

cases = r"""
static void setup(void)
{
    assert(!action && !codec.refs && !codec.locked && primary.secondary != &secondary);
    codec = (struct device) { .i2c = true, .registered = true,
                              .acpi = &realtek, .fwnode = &primary };
    primary.secondary = NULL;
    add_error = devm_error = 0;
    added = removed = warnings = 0;
    hide_codec = false;
}

static void detach(void)
{
    assert(action);
    action(action_data);
    action_data = NULL;
    action = NULL;
    assert(!codec.refs && !codec.locked);
}

int main(void)
{
    setup();
    assert(match_rt5659_client(&codec, NULL));
    codec.i2c = false;
    assert(!match_rt5659_client(&codec, NULL));
    codec.i2c = true;
    codec.acpi = &lookalike;
    assert(!match_rt5659_client(&codec, NULL));
    codec.acpi = NULL;
    assert(!match_rt5659_client(&codec, NULL));

    setup();
    xiaomi_mipad2_init_rt5659(&board);
    assert(added == 1 && !removed && !warnings && codec.refs == 1);
    assert(codec.fwnode == &primary && primary.secondary == &secondary);
    detach();
    assert(!primary.secondary && removed == 1);

    setup();
    primary.secondary = &foreign;
    xiaomi_mipad2_init_rt5659(&board);
    assert(primary.secondary == &foreign && warnings == 1);
    assert(!added && !removed && !codec.refs && !action);

    setup();
    primary.secondary = &absent;
    xiaomi_mipad2_init_rt5659(&board);
    assert(primary.secondary == &secondary && added == 1 && !warnings);
    primary.secondary = &foreign;
    detach();
    assert(primary.secondary == &foreign && !removed);

    setup();
    devm_error = -ENOMEM;
    xiaomi_mipad2_init_rt5659(&board);
    assert(added == 1 && removed == 1 && warnings == 1);
    assert(!primary.secondary && !codec.refs && !action);

    setup();
    add_error = -ENOMEM;
    xiaomi_mipad2_init_rt5659(&board);
    assert(!primary.secondary && !codec.refs && !action);
    assert(!added && !removed && warnings == 1);

    setup();
    codec.registered = false;
    xiaomi_mipad2_init_rt5659(&board);
    assert(!added && !codec.refs && warnings == 1);

    setup();
    codec.fwnode = NULL;
    xiaomi_mipad2_init_rt5659(&board);
    assert(!added && !codec.refs && warnings == 1);

    setup();
    hide_codec = true;
    xiaomi_mipad2_init_rt5659(&board);
    assert(!added && !removed && !codec.refs && warnings == 1);

    puts("PASS: RT5659 ACPI identity, owned attachment, teardown and error paths");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-rt5659-node-") as temp:
    test, binary = Path(temp) / "test.c", Path(temp) / "test"
    test.write_text(mocks + "\n" + "\n".join(functions) + "\n" + cases)
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
