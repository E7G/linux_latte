#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the RT5659 ACPI match and owned board property teardown."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
resolver = (root / "include/linux/platform_data/x86/cht-rt5659.h").read_text()
resolver = "\n".join(line for line in resolver.splitlines() if not line.startswith("#include"))
source = (root / "drivers/platform/x86/x86-android-tablets/other.c").read_text()
functions = []
for name in ("xiaomi_mipad2_remove_rt5659_node",
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
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define __init
#define EPROBE_DEFER 517
#define ERR_PTR(err) ((struct device *)(intptr_t)(err))
#define PTR_ERR(ptr) ((long)(intptr_t)(ptr))
#define IS_ERR(ptr) ((uintptr_t)(ptr) >= (uintptr_t)-4095)
#define ACPI_SUCCESS(status) ((status) == 0)

typedef const void *acpi_handle;

struct software_node { const char *name; };
struct fwnode_handle { struct fwnode_handle *secondary; const struct software_node *node; };
struct acpi_device { const char *hid; acpi_handle handle; };
struct device {
    bool i2c, registered, locked;
    unsigned int refs;
    struct acpi_device *acpi;
    struct fwnode_handle *fwnode;
};

static const struct software_node rt5659_swnode = { "rt5659" };
static struct fwnode_handle secondary = { .node = &rt5659_swnode };
static struct fwnode_handle foreign, primary, absent;
static const int preferred, other_handle, i2c_bus_type;
static struct acpi_device realtek = { "10EC5659", &preferred };
static struct acpi_device alternate = { "10EC5659", &other_handle };
static struct acpi_device lookalike = { "10EC56590", &preferred };
static struct device codec, other_codec, board;
static bool hide_codec, show_alternate, have_path;
static unsigned int added, removed, warnings;
static int add_error, devm_error;
static void (*action)(void *);
static void *action_data;

#define ACPI_COMPANION(dev) ((dev)->acpi)
#define ACPI_HANDLE(dev) ((dev)->acpi ? (dev)->acpi->handle : NULL)
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

static int acpi_get_handle(void *parent, const char *path, acpi_handle *handle)
{
    assert(!parent && !strcmp(path, "\\_SB_.PCI0.I2C2.RTK3"));
    if (!have_path)
        return -ENODEV;
    *handle = &preferred;
    return 0;
}

static int bus_for_each_dev(const int *bus, const void *start, void *data,
                            int (*match)(struct device *, void *))
{
    int ret = 0;
    assert(bus == &i2c_bus_type && !start);
    if (show_alternate)
        ret = match(&other_codec, data); /* Deliberately visited first. */
    return ret || hide_codec ? ret : match(&codec, data);
}

static struct device *get_device(struct device *dev)
{
    assert(dev == &codec || dev == &other_codec);
    dev->refs++;
    return dev;
}

static void put_device(struct device *dev)
{
    if (!dev)
        return;
    assert((dev == &codec || dev == &other_codec) && dev->refs && !dev->locked);
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
    assert(!action && !codec.refs && !other_codec.refs && !codec.locked &&
           primary.secondary != &secondary);
    codec = (struct device) { .i2c = true, .registered = true,
                              .acpi = &realtek, .fwnode = &primary };
    primary.secondary = NULL;
    other_codec = (struct device) { .i2c = true, .registered = true, .acpi = &alternate };
    add_error = devm_error = 0;
    added = removed = warnings = 0;
    hide_codec = show_alternate = false;
    have_path = true;
}

static void detach(void)
{
    assert(action);
    action(action_data);
    action_data = NULL;
    action = NULL;
    assert(!codec.refs && !codec.locked);
}

static void check_resolver(void)
{
    struct device *dev;

    setup();
    show_alternate = true;
    dev = cht_rt5659_find_codec(true);
    assert(dev == &codec && !other_codec.refs && codec.refs == 1);
    put_device(dev);
    assert(PTR_ERR(cht_rt5659_find_codec(false)) == -ENOTUNIQ);
    assert(!codec.refs && !other_codec.refs);

    hide_codec = true;
    assert(PTR_ERR(cht_rt5659_find_codec(true)) == -EPROBE_DEFER);
    assert(!codec.refs && !other_codec.refs);
    have_path = false;
    dev = cht_rt5659_find_codec(true);
    assert(dev == &other_codec && other_codec.refs == 1);
    put_device(dev);
    show_alternate = false;
    assert(PTR_ERR(cht_rt5659_find_codec(false)) == -EPROBE_DEFER);

    setup();
    codec.i2c = false;
    assert(PTR_ERR(cht_rt5659_find_codec(true)) == -EPROBE_DEFER);
    codec.i2c = true;
    codec.acpi = &lookalike;
    assert(PTR_ERR(cht_rt5659_find_codec(false)) == -EPROBE_DEFER);
    codec.acpi = NULL;
    assert(PTR_ERR(cht_rt5659_find_codec(false)) == -EPROBE_DEFER);
    assert(!codec.refs && !other_codec.refs);
}

int main(void)
{
    check_resolver();

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
    test.write_text(mocks + "\n" + resolver + "\n" + "\n".join(functions) + "\n" + cases)
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
