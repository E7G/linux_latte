#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the production ACM and serial activation functions with stub endpoints."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


ROOT = Path(os.environ.get("MIPAD2_KERNEL_SOURCE", Path(__file__).resolve().parents[2]))


def extract(filename, signature):
    text = (ROOT / "drivers/usb/gadget/function" / filename).read_text()
    match = re.search(r"^" + signature + r"\(.*?^}", text, re.M | re.S)
    if not match:
        raise SystemExit(f"Activation function missing: {signature}")
    return match[0]


STUBS = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef uint8_t u8;
#define MAX_U_SERIAL_PORTS 2
#define pr_err(...) ((void)0)
#define pr_debug(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define dev_vdbg(...) ((void)0)
#define pr_warn_ratelimited(...) ((void)++warnings)
#define spin_lock_irqsave(lock, flags) ((flags) = 0, assert(!*(lock)), *(lock) = 1)
#define spin_unlock_irqrestore(lock, flags) ((void)(flags), assert(*(lock)), *(lock) = 0)

struct usb_ep {
    bool enabled;
    void *desc, *driver_data;
    int enable_error, config_error;
    unsigned enables, disables;
};
struct gs_port;
struct gserial {
    struct usb_ep *in, *out;
    struct gs_port *ioport;
    unsigned port_line_coding;
    void (*connect)(struct gserial *), (*disconnect)(struct gserial *);
};
struct gs_port {
    struct gserial *port_usb;
    struct { int count; } port;
    int port_lock, port_num, console_error;
    unsigned port_line_coding;
};
static struct { struct gs_port *port; } ports[MAX_U_SERIAL_PORTS];
struct usb_composite_dev { void *gadget; };
struct usb_configuration { struct usb_composite_dev *cdev; };
struct f_acm;
struct usb_function { struct usb_configuration *config; struct f_acm *acm; };
struct f_acm {
    struct gserial port;
    struct usb_ep *notify;
    unsigned int ctrl_id, data_id;
    u8 port_num;
};

static unsigned starts, warnings, detaches;
static struct f_acm *func_to_acm(struct usb_function *f) { return f->acm; }
static int usb_ep_enable(struct usb_ep *ep)
{
    ++ep->enables;
    if (ep->enable_error)
        return ep->enable_error;
    ep->enabled = true;
    return 0;
}
static void usb_ep_disable(struct usb_ep *ep)
{
    ++ep->disables;
    ep->enabled = false;
    ep->desc = NULL;
}
static int config_ep_by_speed(void *g, struct usb_function *f, struct usb_ep *ep)
{
    (void)g;
    (void)f;
    if (ep->config_error)
        return ep->config_error;
    ep->desc = ep;
    return 0;
}
static void gs_start_io(struct gs_port *port)
{
    assert(port->port_lock && port->port_usb && port->port_usb->ioport == port);
    ++starts;
}
static int gs_console_connect(struct gs_port *port)
{
    assert(port->port_lock);
    return port->console_error;
}
static void gserial_disconnect(struct gserial *gser)
{
    if (!gser->ioport)
        return;
    ++detaches;
    gser->ioport->port_usb = NULL;
    gser->ioport = NULL;
    usb_ep_disable(gser->in);
    usb_ep_disable(gser->out);
}
"""


CASES = r"""
int main(void)
{
    enum test_case {
        NOTIFY, NOTIFY_FAIL, NOTIFY_CONFIG_FAIL, DATA, DATA_CONFIG_FAIL,
        IN_FAIL, OUT_FAIL, CONSOLE_FAIL, RESET_DATA, BAD_INTERFACE, CASE_COUNT
    };
    unsigned failed = 0;
    for (unsigned test = 0; test < CASE_COUNT; ++test) {
        struct usb_ep in = {0}, out = {0}, notify = {0};
        struct gs_port port = {.port.count = 1, .port_line_coding = 42};
        struct f_acm acm = {.port = {.in = &in, .out = &out},
                            .notify = &notify, .ctrl_id = 1, .data_id = 2};
        struct usb_composite_dev cdev = {0};
        struct usb_configuration config = {.cdev = &cdev};
        struct usb_function f = {.config = &config, .acm = &acm};
        int expected = 0;
        bool data = test == DATA || test == CONSOLE_FAIL || test == RESET_DATA;
        unsigned interface = test <= NOTIFY_CONFIG_FAIL ? acm.ctrl_id : acm.data_id;
        starts = warnings = detaches = 0;
        ports[0].port = &port;
        switch (test) {
        case NOTIFY_FAIL:          expected = notify.enable_error = -EIO; break;
        case NOTIFY_CONFIG_FAIL:   expected = notify.config_error = -EINVAL; break;
        case DATA_CONFIG_FAIL:     expected = out.config_error = -EINVAL; break;
        case IN_FAIL:              expected = in.enable_error = -EPIPE; break;
        case OUT_FAIL:             expected = out.enable_error = -ENOSPC; break;
        case CONSOLE_FAIL:         port.console_error = -ENOMEM; break;
        case BAD_INTERFACE:        interface = 3; expected = -EINVAL; break;
        case RESET_DATA:
            in.enabled = out.enabled = true;
            in.desc = &in;
            out.desc = &out;
            acm.port.ioport = &port;
            port.port_usb = &acm.port;
            break;
        default: break;
        }
        int result = acm_set_alt(&f, interface, 0);
        if (result != expected || in.enabled != data || out.enabled != data ||
            notify.enabled != (test == NOTIFY) ||
            acm.port.ioport != (data ? &port : NULL) ||
            port.port_usb != (data ? &acm.port : NULL) ||
            (data && acm.port.port_line_coding != 42) || starts != data ||
            warnings != (test == CONSOLE_FAIL) || detaches != (test == RESET_DATA) ||
            (test == DATA_CONFIG_FAIL && (in.desc || out.desc)) ||
            (test == OUT_FAIL && (in.disables != 1 || !out.enables))) {
            fprintf(stderr, "ACM case %u returned %d (expected %d) and endpoint state %u/%u/%u\n",
                    test, result, expected, in.enabled, out.enabled, notify.enabled);
            ++failed;
        }
        ports[0].port = NULL;
    }
    if (failed)
        return 1;
    printf("PASS: %u ACM activation and recovery cases\n", (unsigned)CASE_COUNT);
    return 0;
}
"""


with tempfile.TemporaryDirectory(prefix="mipad2-acm-activation-") as scratch:
    cfile, binary = Path(scratch) / "probe.c", Path(scratch) / "probe"
    cfile.write_text("\n".join((
        STUBS,
        extract("u_serial.c", "int gserial_connect"),
        extract("f_acm.c", "static int acm_set_alt"),
        CASES,
    )))
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", str(cfile), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
