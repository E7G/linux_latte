#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise ACPI/DMI I2C enumeration order without touching hardware."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[2] /
          "drivers/platform/x86/x86-android-tablets/core.c").read_text()
fragments = []
for pattern in (r"^struct x86_i2c_addr_match \{\n.*?^\};",
                r"^static int match_i2c_client_addr\([^{};]*?^\{\n.*?^\}",
                r"^static __init int x86_instantiate_i2c_client\([^{};]*?^\{\n.*?^\}"):
    matches = re.findall(pattern, source, re.M | re.S)
    if len(matches) != 1:
        raise SystemExit(f"expected a unique production fragment: {pattern}")
    fragments.extend(matches)

mocks = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>

typedef uint16_t u16;
#define __init

struct i2c_client;
struct device { unsigned int refs; struct i2c_client *client; };
struct i2c_adapter { struct device dev; };
struct i2c_client { struct device dev; struct i2c_adapter *adapter; u16 addr; };
struct i2c_board_info { u16 addr; int irq; const char *type; };
struct x86_i2c_client_info {
    struct i2c_board_info board_info;
    const char *adapter_path;
    int irq_data;
};
struct x86_dev_info { const struct x86_i2c_client_info *i2c_client_info; bool use_pci; };

static struct i2c_adapter adapter, other_adapter;
static struct i2c_client existing, created, error_client, *i2c_clients[2];
static struct device unrelated;
static int i2c_bus_type, irq_result, new_error;
static unsigned int pci_lookups, acpi_lookups, irq_calls, create_calls, warnings;
static bool have_adapter, have_existing;

#define pr_err(...) ((void)0)
#define dev_warn(dev, ...) ((void)(dev), warnings++)
#define IS_ERR(client) ((client) == &error_client)
#define PTR_ERR(client) (assert(IS_ERR(client)), new_error)

static int dev_err_probe(struct device *dev, int error, const char *fmt, int idx)
{
    assert(dev == &adapter.dev && fmt && (idx == 0 || idx == 1));
    return error;
}

static void put_device(struct device *dev)
{
    assert(dev->refs > 0);
    dev->refs--;
}

static struct i2c_client *i2c_verify_client(struct device *dev)
{
    return dev->client;
}

static struct i2c_adapter *get_adapter(const struct x86_i2c_client_info *info)
{
    assert(info->adapter_path);
    if (!have_adapter)
        return NULL;
    adapter.dev.refs++;
    return &adapter;
}

static struct i2c_adapter *get_i2c_adap_by_handle(const struct x86_i2c_client_info *info)
{
    acpi_lookups++;
    return get_adapter(info);
}

static struct i2c_adapter *get_i2c_adap_by_pci_parent(const struct x86_i2c_client_info *info)
{
    pci_lookups++;
    return get_adapter(info);
}

static struct device *bus_find_device(const int *bus, const void *start,
                                      const void *data,
                                      int (*match)(struct device *, const void *))
{
    assert(bus == &i2c_bus_type && !start && adapter.dev.refs == 1);
    assert(!match(&unrelated, data));
    if (!have_existing || !match(&existing.dev, data))
        return NULL;
    existing.dev.refs++;
    return &existing.dev;
}

static int x86_acpi_irq_helper_get(const int *data)
{
    assert(data);
    irq_calls++;
    return irq_result;
}

static struct i2c_client *i2c_new_client_device(struct i2c_adapter *adap,
                                                const struct i2c_board_info *board)
{
    assert(adap == &adapter && adap->dev.refs == 1 && board->irq == irq_result);
    create_calls++;
    return new_error ? &error_client : &created;
}
"""

tests = r"""
static const struct x86_i2c_client_info board[] = {
    { .board_info = { .type = "hid-over-i2c", .addr = 0x38 },
      .adapter_path = "\\_SB_.PCI0.I2C6", .irq_data = 77 },
    { .board_info = { .type = "tfa9890", .addr = 0x34 },
      .adapter_path = "\\_SB_.PCI0.I2C2" },
};

static void reset(void)
{
    assert(!adapter.dev.refs && !existing.dev.refs);
    pci_lookups = acpi_lookups = irq_calls = create_calls = warnings = 0;
    i2c_clients[0] = i2c_clients[1] = NULL;
    have_adapter = true;
    have_existing = false;
    existing = (struct i2c_client) { .dev.client = &existing,
                                    .adapter = &adapter, .addr = 0x38 };
    irq_result = 145;
    new_error = 0;
}

static void verify(bool use_pci)
{
    const struct x86_dev_info info = { .i2c_client_info = board, .use_pci = use_pci };

    reset();
    have_existing = true;
    irq_result = -EBUSY;
    assert(!x86_instantiate_i2c_client(&info, 0));
    assert(warnings == 1 && !irq_calls && !create_calls && !i2c_clients[0]);
    assert(!existing.dev.refs && !adapter.dev.refs);
    /* A skipped FTSC1000 must not prevent the next board child probing. */
    irq_result = 0;
    assert(!x86_instantiate_i2c_client(&info, 1));
    assert(irq_calls == 1 && create_calls == 1 && i2c_clients[1] == &created);
    assert(!adapter.dev.refs && !existing.dev.refs);
    assert(pci_lookups == (use_pci ? 2U : 0U) && acpi_lookups == (use_pci ? 0U : 2U));

    reset();
    have_existing = true;
    existing.adapter = &other_adapter;
    assert(!x86_instantiate_i2c_client(&info, 0));
    assert(irq_calls == 1 && create_calls == 1 && i2c_clients[0] == &created);
    assert(!warnings);

    reset();
    have_existing = true;
    existing.addr = 0x39;
    assert(!x86_instantiate_i2c_client(&info, 0));
    assert(irq_calls == 1 && create_calls == 1 && i2c_clients[0] == &created);

    reset();
    assert(!x86_instantiate_i2c_client(&info, 0));
    assert(irq_calls == 1 && create_calls == 1 && i2c_clients[0] == &created);

    reset();
    irq_result = -EIO;
    assert(x86_instantiate_i2c_client(&info, 0) == -EIO);
    assert(irq_calls == 1 && !create_calls && !warnings && !i2c_clients[0]);
    assert(!adapter.dev.refs);

    reset();
    new_error = -EBUSY;
    assert(x86_instantiate_i2c_client(&info, 0) == -EBUSY);
    assert(irq_calls == 1 && create_calls == 1 && !i2c_clients[0]);
    assert(!adapter.dev.refs);

    reset();
    have_adapter = false;
    assert(x86_instantiate_i2c_client(&info, 0) == -ENODEV);
    assert(!irq_calls && !create_calls && !warnings && !i2c_clients[0]);
}

int main(void)
{
    verify(false);
    verify(true);
    puts("PASS: duplicate FTSC1000 leaves IRQ untouched; fallback and errors keep refcounts");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-i2c-fallback-") as temp:
    test, exe = Path(temp) / "test.c", Path(temp) / "test"
    test.write_text(mocks + "\n" + "\n".join(fragments) + "\n" + tests)
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(test), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
