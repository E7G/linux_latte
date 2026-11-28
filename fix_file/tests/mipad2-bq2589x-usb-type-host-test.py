#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the 7.2 BQ2589x status and IRQ path with a modeled I2C register bank."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


root = Path(__file__).resolve().parents[2]
driver = (root / "drivers/power/supply/bq25890_charger.c").read_text()


def extract(pattern):
    matches = re.findall(pattern, driver, re.M | re.S)
    if len(matches) != 1:
        raise SystemExit(f"expected one production fragment: {pattern!r}")
    return matches[0]


def function(name):
    return extract(r"^static [^\n]+ " + name + r"\([^{};]*?^\{\n.*?^\}")


defs = "\n".join(
    extract(r"^#define " + name + r"[ \t][^\n]*")
    for name in ("BQ25890_STATUS_REG", "BQ25890_STATUS_VBUS",
                 "BQ25890_STATUS_CHG", "BQ25890_STATUS_PG", "BQ25890_STATUS_VSYS")
)
decls = "\n".join(
    extract(r"^" + name + r" \{\n.*?^\};")
    for name in ("enum bq25890_chip_version", "enum bq25890_fields",
                 "struct bq25890_state")
)
production = "\n".join(function(name) for name in (
    "bq25890_has_usb_detection",
    "bq25890_decode_usb_type",
    "bq25890_get_usb_type",
    "bq25890_get_chip_state",
    "__bq25890_handle_irq",
))

code = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((BIT((h) + 1) - 1) & ~(BIT(l) - 1))
#define FIELD_GET(mask, value) (((value) & (mask)) >> __builtin_ctz(mask))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof(*(a)))
#define dev_dbg(dev, ...) ((void)(dev))
#define dev_err(dev, ...) ((void)(dev))

enum power_supply_usb_type {
    POWER_SUPPLY_USB_TYPE_UNKNOWN,
    POWER_SUPPLY_USB_TYPE_SDP,
    POWER_SUPPLY_USB_TYPE_DCP,
    POWER_SUPPLY_USB_TYPE_CDP,
};

enum irq_result { IRQ_NONE, IRQ_HANDLED };
typedef enum irq_result irqreturn_t;
enum {
    NTC_FAULT_COLD = 5,
    NTC_FAULT_HOT = 6,
    BQ25895_NTC_FAULT_BUCK_COLD = 1,
    BQ25895_NTC_FAULT_BUCK_HOT = 2,
};
""" + defs + "\n" + decls + r"""

struct stub {
    unsigned int reg0b;
    int reg_error;
    int field_error;
    int write_error;
    unsigned int reads;
    unsigned int field_reads;
    unsigned int events;
    unsigned int adc_writes;
    unsigned int hiz_writes;
    int adc;
    int fields[F_MAX_FIELDS];
};

struct bq25890_device {
    enum bq25890_chip_version chip_version;
    struct stub *rmap;
    struct stub *charger;
    struct stub *dev;
    struct bq25890_state state;
    bool force_hiz;
};

static int regmap_read(struct stub *map, unsigned int reg, unsigned int *value)
{
    assert(reg == 0x0b);
    map->reads++;
    if (map->reg_error)
        return map->reg_error;
    *value = map->reg0b;
    return 0;
}

static int bq25890_field_read(struct bq25890_device *bq, enum bq25890_fields id)
{
    struct stub *map = bq->rmap;

    assert(id == F_EN_HIZ || id == F_BOOST_FAULT || id == F_BAT_FAULT ||
           id == F_CHG_FAULT || id == F_NTC_FAULT);
    map->field_reads++;
    return map->field_error ? map->field_error : map->fields[id];
}

static int bq25890_field_write(struct bq25890_device *bq, enum bq25890_fields id, int val)
{
    struct stub *map = bq->rmap;

    if (map->write_error)
        return map->write_error;
    switch (id) {
    case F_CONV_RATE:
        map->adc = val;
        map->adc_writes++;
        break;
    case F_EN_HIZ:
        map->fields[id] = val;
        map->hiz_writes++;
        break;
    default:
        assert(!"a status refresh must not write charging parameters");
    }
    return 0;
}

static void power_supply_changed(struct stub *charger)
{
    charger->events++;
}
""" + production + r"""

static const int types[] = {
    POWER_SUPPLY_USB_TYPE_UNKNOWN, POWER_SUPPLY_USB_TYPE_SDP,
    POWER_SUPPLY_USB_TYPE_CDP, POWER_SUPPLY_USB_TYPE_DCP,
    POWER_SUPPLY_USB_TYPE_DCP, POWER_SUPPLY_USB_TYPE_UNKNOWN,
    POWER_SUPPLY_USB_TYPE_UNKNOWN, POWER_SUPPLY_USB_TYPE_UNKNOWN,
};

/* Keep the oracle independent of the production detection predicate. */
static bool internal_bc12(enum bq25890_chip_version chip)
{
    return chip == BQ25890 || chip == BQ25895;
}

static void verify_register(enum bq25890_chip_version chip)
{
    struct stub hw = { 0 };
    struct bq25890_device bq = { .chip_version = chip, .rmap = &hw, .dev = &hw };
    struct bq25890_state state;

    for (unsigned int raw = 0; raw <= 255; raw++) {
        int want_type = internal_bc12(chip) ? types[raw >> 5] : POWER_SUPPLY_USB_TYPE_UNKNOWN;

        hw.reg0b = raw;
        hw.reads = hw.field_reads = 0;
        assert(!bq25890_get_chip_state(&bq, &state));
        assert(hw.reads == 1 && hw.field_reads == 5);
        assert(state.chrg_status == ((raw >> 3) & 3));
        assert(state.online == ((raw >> 2) & 1));
        assert(state.vsys_status == (raw & 1));
        assert(state.usb_type == want_type);
        assert(bq25890_get_usb_type(&bq) == want_type);
        assert(hw.reads == (internal_bc12(chip) ? 2U : 1U));
    }
}

static void verify_reclassification(enum bq25890_chip_version chip)
{
    for (unsigned int old = 0; old < 8; old++) {
        for (unsigned int new = 0; new < 8; new++) {
            struct stub hw = { .reg0b = (old << 5) | 0x14, .adc = 1 };
            struct bq25890_device bq = {
                .chip_version = chip, .rmap = &hw, .dev = &hw, .charger = &hw,
            };
            bool changed = internal_bc12(chip) && types[old] != types[new];

            assert(!bq25890_get_chip_state(&bq, &bq.state));
            hw.reg0b = (new << 5) | 0x14;  /* Keep PG and charging state unchanged. */
            assert(__bq25890_handle_irq(&bq) == (changed ? IRQ_HANDLED : IRQ_NONE));
            assert(hw.events == (unsigned int)changed);
            assert(!hw.adc_writes && !hw.hiz_writes && hw.adc == 1);
            assert(bq.state.usb_type ==
                   (internal_bc12(chip) ? types[new] : POWER_SUPPLY_USB_TYPE_UNKNOWN));
            assert(__bq25890_handle_irq(&bq) == IRQ_NONE && hw.events == (unsigned int)changed);
        }
    }
}

static void verify_errors_and_existing_transitions(void)
{
    struct stub hw = { .reg0b = 0 };
    struct bq25890_device bq = {
        .chip_version = BQ25890, .rmap = &hw, .dev = &hw, .charger = &hw,
    };

    assert(!bq25890_get_chip_state(&bq, &bq.state));
    hw.reg0b = 0x74;  /* DCP + fast charging + PG. */
    hw.reg_error = -EIO;
    assert(bq25890_get_usb_type(&bq) == -EIO);
    assert(__bq25890_handle_irq(&bq) == IRQ_NONE);
    assert(!hw.events && !hw.adc_writes && !bq.state.online);
    hw.reg_error = 0;
    hw.field_error = -ENXIO;
    assert(__bq25890_handle_irq(&bq) == IRQ_NONE);
    assert(!hw.events && !hw.adc_writes && !bq.state.online);
    hw.field_error = 0;
    hw.write_error = -EIO;
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(!hw.events && !bq.state.online);
    hw.write_error = 0;
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(hw.events == 1 && hw.adc_writes == 1 && hw.adc == 1 && bq.state.online);
    assert(__bq25890_handle_irq(&bq) == IRQ_NONE);
    hw.reg0b = 0;
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(hw.events == 2 && hw.adc_writes == 2 && hw.adc == 0 && !bq.state.online);
    bq.force_hiz = true;
    hw.reg0b = 0x34;  /* SDP + fast charging + PG, with user's HiZ restored. */
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(hw.events == 3 && hw.hiz_writes == 1 && hw.adc_writes == 2);
    assert(bq.state.hiz && bq.state.online && bq.state.usb_type == POWER_SUPPLY_USB_TYPE_SDP);
}

int main(void)
{
    for (enum bq25890_chip_version chip = BQ25890; chip <= BQ25896; chip++) {
        verify_register(chip);
        verify_reclassification(chip);
    }
    verify_errors_and_existing_transitions();
    puts("PASS: BQ2589x USB types, 1024 register states and 256 type transitions");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-bq2589x-") as temp:
    test, binary = Path(temp) / "test.c", Path(temp) / "test"
    test.write_text(code)
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
