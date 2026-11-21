#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile DWC3 soft-connect and its callers with faultable endpoint commands."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


root = Path(os.getenv("MIPAD2_KERNEL_SOURCE", str(Path(__file__).resolve().parents[2])))
gadget = (root / "drivers/usb/dwc3/gadget.c").read_text()
names = ("__dwc3_gadget_start", "dwc3_gadget_soft_connect",
         "dwc3_gadget_pullup", "dwc3_gadget_resume")
source = [re.search(rf"^(?:static )?int {name}\([^;{{]*\)\n\{{.*?^\}}", gadget,
                    re.M | re.S).group() for name in names]

mock = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;

struct device { bool suspended; };
struct dwc3;
struct usb_gadget { struct dwc3 *dwc; };
struct dwc3_ep { char name[4]; int flags, num; bool enabled; };
struct dwc3 {
	struct device *dev;
	struct dwc3_ep *eps[2];
	int imod_interval, hwparams, ep0state, link_state, irq_gadget, connect_mutex;
	bool ep0_bounced, delayed_status, softconnect, pullups_connected, gadget_driver;
};
static struct { uint16_t wMaxPacketSize; } dwc3_gadget_ep0_desc;

#define DWC3_DEV_IMOD(n) (1 + (n))
#define DWC3_GEVNTCOUNT(n) (10 + (n))
#define DWC3_GEVNTCOUNT_EHB 16
#define DWC3_GRXTHRCFG 2
#define DWC3_GRXTHRCFG_PKTCNTSEL 4
#define DWC31_GRXTHRCFG_PKTCNTSEL 8
#define DWC3_DCFG 3
#define DWC3_DCFG_IGNSTRMPP 16
#define DWC3_DCFG1 4
#define DWC3_DCFG1_DIS_MST_ENH 64
#define DWC3_IP_IS(x) true
#define DWC3_MST_CAPABLE(x) true
#define DWC3_DEPCFG_ACTION_INIT 5
#define EP0_SETUP_PHASE 1
#define DWC3_LINK_STATE_SS_DIS 4
#define cpu_to_le16(x) (x)
#define dev_err(...) ((void)0)

static int failed_step, fault, pm_result, pm_balance, pm_resets, barriers;
static char trace[32];
static unsigned int length;
static void mark(char c)
{
	assert(length + 1 < sizeof(trace));
	trace[length++] = c;
	trace[length] = 0;
}

static int status(int this_step)
{
	return this_step == failed_step ? fault : 0;
}

static bool dwc3_has_imod(struct dwc3 *d) { assert(d); return true; }
static u32 dwc3_readl(struct dwc3 *d, int r) { assert(d && r >= 0); return 0; }
static void dwc3_writel(struct dwc3 *d, int r, u32 v) { assert(d && r >= 0); (void)v; }
static void dwc3_gadget_setup_nump(struct dwc3 *d) { assert(d); }
static void dwc3_enable_susphy(struct dwc3 *d, bool on) { assert(d && on); mark('P'); }
static int dwc3_core_soft_reset(struct dwc3 *d) { assert(d); mark('R'); return status(1); }
static int dwc3_event_buffers_setup(struct dwc3 *d) { assert(d); mark('B'); return 0; }
static int dwc3_gadget_start_config(struct dwc3 *d, int n)
{
	assert(d && n == 0);
	mark('C');
	return status(2);
}
static int __dwc3_gadget_ep_enable(struct dwc3_ep *ep, int n)
{
	assert(n == DWC3_DEPCFG_ACTION_INIT && ep->flags == 0 && !ep->enabled);
	mark(ep->num ? '1' : '0');
	int ret = status(3 + ep->num);
	ep->enabled = !ret;
	return ret;
}
static void __dwc3_gadget_ep_disable(struct dwc3_ep *ep)
{
	assert(ep->num == 0 && ep->enabled);
	ep->enabled = false;
	mark('d');
}
static void dwc3_ep0_out_start(struct dwc3 *d)
{
	assert(d->eps[0]->enabled && d->eps[1]->enabled && d->ep0state == EP0_SETUP_PHASE);
	assert(!d->delayed_status && !d->ep0_bounced);
	mark('T');
}
static void dwc3_gadget_enable_irq(struct dwc3 *d) { assert(d); mark('I'); }
static int dwc3_gadget_run_stop(struct dwc3 *d, bool on)
{
	assert(d && on);
	mark('X');
	return status(5);
}
static struct dwc3 *gadget_to_dwc(struct usb_gadget *g) { return g->dwc; }
static void pm_runtime_barrier(struct device *d) { assert(d); barriers++; }
static bool pm_runtime_suspended(struct device *d) { return d->suspended; }
static int pm_runtime_get_sync(struct device *d) { assert(d); pm_balance++; return pm_result; }
static void pm_runtime_put(struct device *d) { assert(d && pm_balance == 1); pm_balance--; }
static void pm_runtime_set_suspended(struct device *d) { d->suspended = true; pm_resets++; }
static void synchronize_irq(int irq) { assert(irq == 9); mark('S'); }
static void mutex_lock(int *m) { assert(!*m); *m = 1; mark('L'); }
static void mutex_unlock(int *m) { assert(*m == 1); *m = 0; mark('U'); }
static int dwc3_gadget_soft_disconnect(struct dwc3 *d)
{
	assert(d && !d->softconnect);
	mark('O');
	return status(6);
}
"""

cases = r"""
static struct device dev;
static struct dwc3_ep ep[2];
static struct usb_gadget g;

static struct dwc3 fixture(void)
{
	dev = (struct device){ 0 };
	ep[0] = (struct dwc3_ep){ .name = "ep0", .flags = 7, .num = 0 };
	ep[1] = (struct dwc3_ep){ .name = "ep1", .flags = 7, .num = 1 };
	length = 0;
	trace[0] = '\0';
	failed_step = fault = pm_balance = pm_resets = barriers = 0;
	pm_result = 1;
	return (struct dwc3) { .dev = &dev, .eps = { &ep[0], &ep[1] },
		.softconnect = true, .gadget_driver = true, .irq_gadget = 9,
		.ep0_bounced = true, .delayed_status = true };
}

int main(void)
{
	const char *sequences[] = { "RBC01TIPX", "R", "RBC", "RBC0", "RBC01d", "RBC01TIPX" };
	const int errs[] = { -EIO, -ETIMEDOUT, -EBUSY, -EINVAL };
	unsigned int count = 0;

	/* Connection, resume helper, active PM pullup. No RUN_STOP on EP0 failure. */
	for (unsigned int caller = 0; caller < 3; caller++) {
		for (int step = 0; step <= 5; step++) {
			for (unsigned int i = 0; i < sizeof(errs) / sizeof(errs[0]); i++) {
				struct dwc3 d = fixture();
				g.dwc = &d;
				failed_step = step;
				fault = errs[i];
				int ret = caller == 2 ? dwc3_gadget_pullup(&g, 1) :
					  caller == 1 ? dwc3_gadget_resume(&d) :
							dwc3_gadget_soft_connect(&d);
				char expected[32];
				snprintf(expected, sizeof(expected), caller == 2 ? "SL%sU" : "%s",
					 sequences[step]);
				assert(ret == (step ? errs[i] : 0));
				assert(!strcmp(trace, expected));
				assert(ep[0].enabled == (step == 0 || step == 5));
				assert(ep[1].enabled == ep[0].enabled && !d.connect_mutex && !pm_balance);
				/* Fault cleared: the next valid attempt can enable both endpoints. */
				if (step >= 2 && step <= 4) {
					length = 0;
					trace[0] = '\0';
					failed_step = 0;
					assert(dwc3_gadget_soft_connect(&d) == 0);
					assert(ep[0].enabled && ep[1].enabled && !strcmp(trace, sequences[0]));
				}
				count++;
			}
		}
	}
	for (unsigned int i = 0; i < 2; i++) {
		struct dwc3 d = fixture();
		d.gadget_driver = i == 0;
		d.softconnect = i == 1;
		assert(dwc3_gadget_resume(&d) == 0 && !length);
		count++;
	}
	for (unsigned int i = 0; i < 5; i++) {
		struct dwc3 d = fixture();
		g.dwc = &d;
		pm_result = i == 0 ? 0 : i == 1 ? -EHOSTDOWN : 1;
		dev.suspended = i == 2;
		d.pullups_connected = i == 3 || i == 4;
		assert(dwc3_gadget_pullup(&g, i != 2 && i != 4) == (i == 1 ? -EHOSTDOWN : 0));
		assert(!strcmp(trace, i == 4 ? "SLOU" : "") && !pm_balance);
		assert(barriers == (i == 2 || i == 4) && pm_resets == (i == 1));
		count++;
	}
	printf("PASS %u DWC3 endpoint/soft-connect/pullup cases; mocked USB/PM\n", count);
	return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-dwc3-gadget-start-") as tmp:
    path = Path(tmp) / "gadget.c"
    exe = Path(tmp) / "test"
    path.write_text("\n".join([mock, *source, cases]))
    cc = shlex.split(os.getenv("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(path), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
