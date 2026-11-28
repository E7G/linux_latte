#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run BQ2589x status, IRQ and system-PM paths with a modeled I2C bank."""
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
                 "BQ25890_STATUS_CHG", "BQ25890_STATUS_PG", "BQ25890_STATUS_VSYS",
                 "BQ25890_FAULT_REG", "BQ25890_FAULT_BOOST", "BQ25890_FAULT_CHG",
                 "BQ25890_FAULT_BAT", "BQ25890_FAULT_NTC", "BQ25890_FAULT_LATCHED")
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
    "bq25890_read_fault",
    "bq25890_get_chip_state",
    "bq25890_apply_chip_state",
    "__bq25890_handle_irq",
    "bq25890_set_online",
    "bq25890_suspend",
    "bq25890_resume",
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
    unsigned int reg0c[2];
    int reg0c_error[2];
    int reg_error;
    int field_error;
    int write_error;
    unsigned int reads;
    unsigned int field_reads;
    unsigned int fault_reads;
    unsigned int warnings;
    unsigned int reported_latched;
    int reported_live;
    bool expect_read_pair;
    char reads_trace[4];
    unsigned int trace_len;
    unsigned int events;
    unsigned int adc_writes;
    unsigned int hiz_writes;
    int adc;
    int fields[F_MAX_FIELDS];
    bool require_lock;
};

struct mutex {
    bool held;
};

static void record_read(struct stub *map, char type)
{
    if (map->expect_read_pair) {
        assert(map->trace_len < sizeof(map->reads_trace));
        map->reads_trace[map->trace_len++] = type;
    }
}

static void record_fault(struct stub *map, unsigned int latched, int live)
{
    map->warnings++;
    map->reported_latched = latched;
    map->reported_live = live;
}
#define dev_warn_ratelimited(dev, fmt, ...) ((void)(fmt), record_fault(dev, __VA_ARGS__))

struct bq25890_device {
    enum bq25890_chip_version chip_version;
    struct stub *rmap;
    struct stub *charger;
    struct stub *dev;
    struct bq25890_state state;
    bool force_hiz;
    bool adc_paused;
    bool resume_pending;
    struct mutex lock;
};

struct device {
    struct bq25890_device *bq;
};

static struct bq25890_device *dev_get_drvdata(struct device *dev)
{
    return dev->bq;
}

static void mutex_lock(struct mutex *lock)
{
    assert(!lock->held);
    lock->held = true;
}

static void mutex_unlock(struct mutex *lock)
{
    assert(lock->held);
    lock->held = false;
}

static int regmap_read(struct stub *map, unsigned int reg, unsigned int *value)
{
    if (reg == 0x0c) {
        unsigned int phase = map->fault_reads++ % 2;

        record_read(map, 'F');
        if (map->reg0c_error[phase])
            return map->reg0c_error[phase];
        *value = map->reg0c[phase];
        return 0;
    }
    assert(reg == 0x0b);
    record_read(map, 'S');
    map->reads++;
    if (map->reg_error)
        return map->reg_error;
    *value = map->reg0b;
    return 0;
}

static int bq25890_field_read(struct bq25890_device *bq, enum bq25890_fields id)
{
    struct stub *map = bq->rmap;

    assert(id == F_EN_HIZ);
    record_read(map, 'H');
    map->field_reads++;
    return map->field_error ? map->field_error : map->fields[id];
}

static int bq25890_field_write(struct bq25890_device *bq, enum bq25890_fields id, int val)
{
    struct stub *map = bq->rmap;

    assert(!map->require_lock || bq->lock.held);
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
        hw.reads = hw.field_reads = hw.fault_reads = 0;
        assert(!bq25890_get_chip_state(&bq, &state, NULL));
        assert(hw.reads == 1 && hw.field_reads == 1 && hw.fault_reads == 2);
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

            assert(!bq25890_get_chip_state(&bq, &bq.state, NULL));
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

    assert(!bq25890_get_chip_state(&bq, &bq.state, NULL));
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

static void verify_fault_register(enum bq25890_chip_version chip)
{
    struct stub hw = { .reg0b = 0x34, .expect_read_pair = true };
    struct bq25890_device bq = { .chip_version = chip, .rmap = &hw, .dev = &hw };
    struct bq25890_state observed;

    for (unsigned int live = 0; live < 256; live++) {
        unsigned int ntc = live & 7;
        unsigned int latched = (live ^ 0xf8) & 0xf8;

        hw.reg0c[0] = latched | ntc;
        hw.reg0c[1] = live;
        hw.trace_len = hw.warnings = 0;
        assert(!bq25890_get_chip_state(&bq, &observed, NULL));
        assert(hw.trace_len == 4 && !memcmp(hw.reads_trace, "SHFF", 4));
        assert(observed.boost_fault == ((live >> 6) & 1));
        assert(observed.chrg_fault == ((live >> 4) & 3));
        assert(observed.bat_fault == ((live >> 3) & 1));
        if (chip == BQ25895 && ntc == 1)
            ntc = 5;
        else if (chip == BQ25895 && ntc == 2)
            ntc = 6;
        assert(observed.ntc_fault == ntc);
        assert(hw.warnings == !!latched);
        if (latched)
            assert(hw.reported_latched == latched && hw.reported_live == (int)(live & 0xf8));
    }
}

static void verify_fault_events_and_failed_transactions(void)
{
    struct stub hw = { .reg0b = 0x34 };
    struct bq25890_device bq = {
        .chip_version = BQ25890, .rmap = &hw, .dev = &hw, .charger = &hw,
    };
    struct bq25890_state previous, output;

    assert(!bq25890_get_chip_state(&bq, &bq.state, NULL));
    /* A historical battery/timer event is logged, but health is now good. */
    hw.reg0c[0] = 0x38;
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(hw.warnings == 1 && hw.reported_latched == 0x38 && !hw.events);
    assert(!bq.state.bat_fault && !bq.state.chrg_fault);

    /* NTC is live on both reads, so a changed TS value is not latched history. */
    hw.reg0c[0] = 5;
    hw.reg0c[1] = 6;
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(hw.warnings == 1 && hw.events == 1 && bq.state.ntc_fault == 6);
    assert(!hw.adc_writes && !hw.hiz_writes);

    /* Failure after either register transaction must not change the destination. */
    output = previous = bq.state;
    hw.reg0b = 0x79; /* Change the status fields too, not only the fault byte. */
    hw.fields[F_EN_HIZ] = 1;
    hw.reg0c_error[0] = -ENXIO;
    assert(bq25890_get_chip_state(&bq, &output, NULL) == -ENXIO);
    assert(!memcmp(&output, &previous, sizeof(previous)) && hw.warnings == 1);
    hw.fault_reads = 0;
    hw.reg0c_error[0] = 0;
    hw.reg0c_error[1] = -EIO;
    hw.reg0c[0] = 0x40;
    assert(bq25890_get_chip_state(&bq, &output, NULL) == -EIO);
    assert(!memcmp(&output, &previous, sizeof(previous)));
    assert(hw.warnings == 2 && hw.reported_latched == 0x40 && hw.reported_live == -EIO);
    assert(__bq25890_handle_irq(&bq) == IRQ_HANDLED);
    assert(hw.warnings == 3 && hw.reported_live == -EIO);
    assert(!memcmp(&bq.state, &previous, sizeof(previous)) && hw.events == 1);
}

static irqreturn_t fire_irq(struct bq25890_device *bq)
{
    irqreturn_t ret;

    mutex_lock(&bq->lock);
    ret = __bq25890_handle_irq(bq);
    mutex_unlock(&bq->lock);
    return ret;
}

static void verify_sleep_and_hiz(void)
{
    struct stub hw = { .reg0b = 0x34, .adc = 1, .require_lock = true };
    struct bq25890_device bq = {
        .chip_version = BQ25890, .rmap = &hw, .charger = &hw, .dev = &hw,
    };
    struct device dev = { .bq = &bq };

    assert(!bq25890_get_chip_state(&bq, &bq.state, NULL));
    assert(!bq25890_suspend(&dev));
    assert(bq.adc_paused && !hw.adc && hw.adc_writes == 1 && !bq.lock.held);
    hw.reg0b = 0;
    assert(fire_irq(&bq) == IRQ_HANDLED);
    hw.reg0b = 0x74;
    assert(fire_irq(&bq) == IRQ_HANDLED);
    assert(hw.events == 2 && hw.adc_writes == 1 && !hw.adc);
    assert(!bq25890_resume(&dev));
    assert(hw.events == 3 && hw.adc_writes == 2 && hw.adc == 1);
    assert(!bq.adc_paused && !bq.resume_pending && !bq.lock.held);

    assert(!bq25890_set_online(&bq, false));
    assert(hw.events == 4 && hw.hiz_writes == 1 && hw.adc_writes == 3 && !hw.adc);
    assert(bq.force_hiz && bq.state.hiz && !bq.lock.held);
    assert(!bq25890_suspend(&dev));
    /* A replug while asleep resets HiZ; power-good has not changed. */
    hw.fields[F_EN_HIZ] = 0;
    assert(!bq25890_resume(&dev));
    assert(bq.state.online && bq.state.hiz && bq.force_hiz && !hw.adc);
    assert(hw.hiz_writes == 2 && hw.adc_writes == 5 && hw.events == 5);
    assert(!bq25890_set_online(&bq, true));
    assert(!bq.force_hiz && !bq.state.hiz && hw.adc == 1);

    /* Detach without an IRQ during suspend. */
    assert(!bq25890_suspend(&dev));
    hw.reg0b = 0;
    assert(!bq25890_resume(&dev));
    assert(!bq.state.online && !hw.adc && hw.events == 7);
}

static void verify_sleep_failures(void)
{
    struct stub hw = { .reg0b = 0x34, .adc = 1, .require_lock = true };
    struct bq25890_device bq = {
        .chip_version = BQ25890, .rmap = &hw, .charger = &hw, .dev = &hw,
    };
    struct device dev = { .bq = &bq };
    struct bq25890_state original;

    assert(!bq25890_get_chip_state(&bq, &bq.state, NULL));
    original = bq.state;
    hw.write_error = -EIO;
    assert(bq25890_suspend(&dev) == -EIO);
    assert(!bq.adc_paused && hw.adc == 1 && !bq.lock.held);
    assert(bq25890_set_online(&bq, false) == -EIO);
    assert(!bq.force_hiz && !bq.state.hiz);

    hw.write_error = 0;
    assert(!bq25890_suspend(&dev));
    hw.reg0b = 0x74;  /* A different USB type is available after resume. */
    hw.field_error = -ENXIO; /* Failure after the status register was read. */
    assert(bq25890_resume(&dev) == -ENXIO);
    assert(!bq.adc_paused && bq.resume_pending && !bq.lock.held);
    assert(!memcmp(&original, &bq.state, sizeof(original)) && !hw.events);
    hw.field_error = 0;
    hw.write_error = -EIO;
    assert(fire_irq(&bq) == IRQ_HANDLED);
    assert(bq.resume_pending && !hw.adc && !hw.events);
    assert(!memcmp(&original, &bq.state, sizeof(original)));

    /* A retry must run even if the next status is unchanged again. */
    hw.reg0b = 0x34;
    hw.write_error = 0;
    assert(fire_irq(&bq) == IRQ_HANDLED);
    assert(!bq.resume_pending && hw.adc == 1 && hw.events == 1);
    assert(fire_irq(&bq) == IRQ_NONE && hw.events == 1);
}

/* Combine a replug, a read-to-clear event, and retry of a PM restore. */
static void verify_fault_during_resume(bool user_hiz)
{
    struct stub hw = { .reg0b = 0x34, .adc = 1, .require_lock = true };
    struct bq25890_device bq = {
        .chip_version = BQ25890, .rmap = &hw, .charger = &hw, .dev = &hw,
    };
    struct device dev = { .bq = &bq };
    struct bq25890_state original;
    unsigned int event_count, adc_writes, hiz_writes;

    assert(!bq25890_get_chip_state(&bq, &bq.state, NULL));
    if (user_hiz)
        assert(!bq25890_set_online(&bq, false));
    original = bq.state;
    event_count = hw.events;
    hiz_writes = hw.hiz_writes;
    assert(!bq25890_suspend(&dev));
    adc_writes = hw.adc_writes;

    /* Same source after replug; hardware has forgotten any HiZ request. */
    hw.fields[F_EN_HIZ] = 0;
    hw.reg0c[0] = 0x40;
    hw.reg0c_error[1] = -EIO;
    assert(bq25890_resume(&dev) == -EIO);
    assert(!bq.adc_paused && bq.resume_pending && !bq.lock.held);
    assert(!memcmp(&bq.state, &original, sizeof(original)));
    assert(hw.events == event_count && hw.hiz_writes == hiz_writes);
    assert(!hw.adc && hw.adc_writes == adc_writes);
    assert(hw.warnings == 1 && hw.reported_latched == 0x40 && hw.reported_live == -EIO);

    /* A new latch was consumed by the IRQ; ACK it without publishing. */
    hw.reg0c[0] = 0x08;
    assert(fire_irq(&bq) == IRQ_HANDLED);
    assert(bq.resume_pending && hw.events == event_count && !hw.adc);
    assert(hw.adc_writes == adc_writes && hw.hiz_writes == hiz_writes);
    assert(!memcmp(&bq.state, &original, sizeof(original)));
    assert(hw.warnings == 2 && hw.reported_latched == 0x08 && hw.reported_live == -EIO);

    hw.reg0c[0] = 0;
    hw.reg0c_error[1] = 0;
    assert(fire_irq(&bq) == IRQ_HANDLED);
    assert(!bq.resume_pending && !bq.lock.held);
    assert(hw.events == event_count + 1 && hw.adc_writes == adc_writes + 1);
    assert(hw.hiz_writes == hiz_writes + user_hiz && hw.fields[F_EN_HIZ] == user_hiz);
    assert(hw.adc == !user_hiz);
    assert(!memcmp(&bq.state, &original, sizeof(original)));
    assert(fire_irq(&bq) == IRQ_NONE);
    assert(hw.events == event_count + 1 && hw.warnings == 2);
}

int main(void)
{
    for (enum bq25890_chip_version chip = BQ25890; chip <= BQ25896; chip++) {
        verify_register(chip);
        verify_reclassification(chip);
        verify_fault_register(chip);
    }
    verify_errors_and_existing_transitions();
    verify_fault_events_and_failed_transactions();
    verify_sleep_and_hiz();
    verify_sleep_failures();
    verify_fault_during_resume(false);
    verify_fault_during_resume(true);
    puts("PASS: BQ2589x USB types, 1024 register states and 256 type transitions");
    puts("PASS: BQ2589x REG0C, 1024 live fault states, latched events and failed reads");
    puts("PASS: BQ2589x suspend/IRQ/resume, HiZ and REG0C recovery");
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
