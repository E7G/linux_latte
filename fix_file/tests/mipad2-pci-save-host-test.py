#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the real IUNIT snapshot and probe's save-to-cleanup control flow."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


root = Path(os.getenv("MIPAD2_KERNEL_SOURCE", str(Path(__file__).resolve().parents[2])))
atomisp = root / "drivers/staging/media/atomisp"
source = (atomisp / "pci/atomisp_v4l2.c").read_text()
regs = (atomisp / "pci/atomisp-regs.h").read_text()
rev = (atomisp / "include/linux/atomisp.h").read_text()
pci = (root / "include/linux/pci.h").read_text()
std_pci = (root / "include/uapi/linux/pci_regs.h").read_text()
internal = (atomisp / "pci/atomisp_internal.h").read_text()
snapshot = re.search(r"^static int atomisp_save_iunit_reg\(.*?^\}", source,
                     re.M | re.S).group()
probe = re.search(r"^static int atomisp_pci_probe\(.*?^\}", source, re.M | re.S).group()
probe_start = re.search(r"^\s*/\* Save the IUNIT context.*?\*/", probe, re.M | re.I)
probe = probe[probe_start.start():]
saved_struct = re.search(r"^struct atomisp_regs \{.*?^\};", internal, re.M | re.S).group()
translator = re.search(r"^static inline int pcibios_err_to_errno\(.*?^\}", pci,
                       re.M | re.S).group()

defs = []
for header, names in (
    (regs, r"PCI_[A-Z_]+|MRFLD_PCI_[A-Z_]+"),
    (rev, r"ATOMISP_HW_(?:REVISION_(?:ISP2401|SHIFT)|STEPPING_B0)"),
    (pci, r"PCIBIOS_[A-Z_]+|PCI_ERROR_RESPONSE|PCI_POSSIBLE_ERROR\(val\)"),
    (std_pci, r"PCI_COMMAND|PCI_INTERRUPT_LINE"),
):
    defs += re.findall(rf"^#define (?:{names})[ \t]+[^\n]+", header, re.M)

includes = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#define BIT(n) (1UL << (n))
#define IRQF_SHARED 128
#define IS_CHT (isp->cht)
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
"""

mock = r"""
struct device { int unused; };
struct pci_dev { struct device dev; int irq; };
struct firmware { int unused; };
struct atomisp_device {
	struct device *dev;
	struct firmware *firmware;
	struct { struct { const void *data; } isp_css_fw; } css_env;
	struct { unsigned int hw_revision; } media_dev;
	struct atomisp_regs saved_regs;
	int notifier;
	bool cht;
};

static struct pci_dev pdev = { .irq = 17 };
static struct firmware fw;
static int read_pos, fail_on, pci_status, fail_setup;
static bool no_csi_response;
static char lifetime[24];
static unsigned int events;

static const struct { int offset, width; } accesses[] = {
	{ 0x04, 2 }, { 0x90, 4 }, { 0x94, 4 }, { 0x98, 2 }, { 0x3c, 1 },
	{ 0x9c, 4 }, { 0x84, 4 }, { 0xfc, 4 }, { 0xd4, 4 }, { 0xf4, 4 },
	{ 0xe4, 4 }, { 0xe8, 4 }, { 0xe0, 4 }, { 0xdc, 4 }, { 0xec, 4 },
};

static void step(char c)
{
	assert(events + 1 < sizeof(lifetime));
	lifetime[events++] = c;
	lifetime[events] = 0;
}

static struct pci_dev *to_pci_dev(struct device *dev)
{
	assert(dev == &pdev.dev);
	return &pdev;
}

static int read_config(struct pci_dev *dev, int offset, int width, u32 *value)
{
	assert(dev == &pdev);
	assert((unsigned int)read_pos < sizeof(accesses) / sizeof(accesses[0]));
	assert(accesses[read_pos].offset == offset && accesses[read_pos].width == width);
	read_pos++;
	*value = read_pos == fail_on || (offset == 0xe8 && no_csi_response)
		? UINT32_MAX : offset == 0x3c ? 0xff : 0x40000000U | (unsigned int)offset;
	return read_pos == fail_on ? pci_status : 0;
}

static int pci_read_config_byte(struct pci_dev *dev, int offset, u8 *value)
{
	u32 raw;
	int ret = read_config(dev, offset, 1, &raw);
	*value = raw;
	return ret;
}

static int pci_read_config_word(struct pci_dev *dev, int offset, u16 *value)
{
	u32 raw;
	int ret = read_config(dev, offset, 2, &raw);
	*value = raw;
	return ret;
}

static int pci_read_config_dword(struct pci_dev *dev, int offset, u32 *value)
{
	return read_config(dev, offset, 4, value);
}

static void hmm_init(void) { step('H'); }
static void hmm_cleanup(void) { step('h'); }
static void atomisp_isr(void) { }
static void atomisp_isr_thread(void) { }
static int devm_request_threaded_irq(struct device *dev, int irq, void (*top)(void),
				    void (*thread)(void), int flags, const char *name,
				    struct atomisp_device *isp)
{
	assert(dev == isp->dev && irq == pdev.irq && top && thread && flags == IRQF_SHARED);
	assert(!strcmp(name, "isp_irq"));
	step('I');
	return fail_setup == 1 ? -EBUSY : 0;
}
static int atomisp_css_load_firmware(struct atomisp_device *isp)
{
	assert(isp->firmware == &fw);
	step('C');
	return fail_setup == 2 ? -ENOEXEC : 0;
}
static void release_firmware(struct firmware *firmware)
{
	assert(firmware == &fw || !firmware);
	step(firmware ? 'F' : 'n');
}
static void atomisp_pm_init(struct atomisp_device *isp) { assert(isp && !isp->firmware); step('P'); }
static void atomisp_pm_uninit(struct atomisp_device *isp) { assert(isp); step('p'); }
static int v4l2_async_nf_register(int *nf)
{
	assert(nf);
	step('N');
	return fail_setup == 3 ? -EAGAIN : 0;
}
static void ia_css_unload_firmware(void) { step('c'); }
static void devm_free_irq(struct device *dev, int irq, struct atomisp_device *isp)
{
	assert(dev == isp->dev && irq == pdev.irq);
	step('i');
}
static void atomisp_unregister_entities(struct atomisp_device *isp) { assert(isp); step('e'); }
static void atomisp_uninitialize_modules(struct atomisp_device *isp) { assert(isp); step('m'); }
static int atomisp_msi_irq_uninit(struct atomisp_device *isp) { assert(isp); step('u'); return 0; }
static void pci_free_irq_vectors(struct pci_dev *dev) { assert(dev == &pdev); step('v'); }
"""

cases = r"""
static const u32 fallback_bar = 0xf1100000;
static const u32 unused_cg = 0x1377;

static void reset(struct atomisp_device *isp)
{
	*isp = (struct atomisp_device){ .dev = &pdev.dev, .firmware = &fw };
	memset(&isp->saved_regs, 0xa5, sizeof(isp->saved_regs));
	isp->saved_regs.ispmmadr = fallback_bar;
	isp->saved_regs.cg_dis = unused_cg;
	lifetime[0] = 0;
	events = read_pos = fail_on = pci_status = fail_setup = 0;
	no_csi_response = false;
}

int main(void)
{
	struct atomisp_device isp;
	unsigned char before[sizeof(isp.saved_regs)];
	unsigned int count = 0;
	static const int errors[][2] = {
		{ PCIBIOS_FUNC_NOT_SUPPORTED, -ENOENT }, { PCIBIOS_BAD_VENDOR_ID, -ENOTTY },
		{ PCIBIOS_DEVICE_NOT_FOUND, -ENODEV }, { PCIBIOS_BAD_REGISTER_NUMBER, -EFAULT },
		{ PCIBIOS_SET_FAILED, -EIO }, { PCIBIOS_BUFFER_TOO_SMALL, -ENOSPC },
		{ 0x90, -ERANGE }, { -ETIMEDOUT, -ETIMEDOUT },
	};
	static const unsigned int revisions[] = { 0x1100, 0x2000, 0x200f, 0x2010, 0x2011 };
	for (unsigned int cht = 0; cht < 2; cht++) {
		for (unsigned int i = 0; i < sizeof(revisions) / sizeof(revisions[0]); i++) {
			reset(&isp);
			isp.cht = cht;
			isp.media_dev.hw_revision = revisions[i];
			assert(probe_tail(&pdev, &isp) == 0);
			assert(read_pos == 15 && !strcmp(lifetime, "HICFPN"));
			assert(isp.saved_regs.pcicmdsts == 4 && isp.saved_regs.intr == 0xff);
			assert(isp.saved_regs.ispmmadr == fallback_bar && isp.saved_regs.cg_dis == unused_cg);
			assert(isp.saved_regs.msicap == (0x40000000 | 0x90));
			assert(isp.saved_regs.msi_addr == (0x40000000 | 0x94) && isp.saved_regs.msi_data == 0x98);
			assert(isp.saved_regs.interrupt_control == (0x40000000 | 0x9c));
			assert(isp.saved_regs.pmcs == (0x40000000 | 0x84));
			assert(isp.saved_regs.i_control == (0x400000fc |
			       MRFLD_PCI_I_CONTROL_ENABLE_READ_COMBINING |
			       MRFLD_PCI_I_CONTROL_ENABLE_WRITE_COMBINING));
			assert(isp.saved_regs.csi_access_viol == (0x40000000 | 0xd4));
			assert(isp.saved_regs.csi_rcomp_config == (0x400000f4 | 0x800000));
			assert(isp.saved_regs.csi_afe_dly == (0x40000000 | 0xe4));
			assert(isp.saved_regs.csi_control ==
			       (0x400000e8 | (i >= 1 ? 0x01000000 : 0) |
				(cht && i >= 3 ? 0x02000000 : 0)));
			assert(isp.saved_regs.csi_afe_rcomp_config == (0x40000000 | 0xe0));
			assert(isp.saved_regs.csi_afe_hs_control == (0x40000000 | 0xdc));
			assert(isp.saved_regs.csi_deadline_control == (0x40000000 | 0xec));
			count++;
		}
	}
	for (int index = 1; index <= 15; index++) {
		for (unsigned int i = 0; i < sizeof(errors) / sizeof(errors[0]); i++) {
			reset(&isp);
			fail_on = index;
			pci_status = errors[i][0];
			memcpy(before, &isp.saved_regs, sizeof(before));
			assert(probe_tail(&pdev, &isp) == errors[i][1]);
			assert(read_pos == index && !strcmp(lifetime, "emuvF"));
			assert(!memcmp(before, &isp.saved_regs, sizeof(before)));
			count++;
		}
	}
	reset(&isp);
	no_csi_response = true;
	memcpy(before, &isp.saved_regs, sizeof(before));
	assert(probe_tail(&pdev, &isp) == -ENODEV);
	assert(read_pos == 12 && !strcmp(lifetime, "emuvF"));
	assert(!memcmp(before, &isp.saved_regs, sizeof(before)));
	count++;

	static const struct { int error; const char *trace; } setup[] = {
		{ -EBUSY, "HIhemuvF" }, { -ENOEXEC, "HICihemuvF" },
		{ -EAGAIN, "HICFPNpcihemuvn" },
	};
	for (unsigned int i = 0; i < sizeof(setup) / sizeof(setup[0]); i++) {
		reset(&isp);
		fail_setup = i + 1;
		assert(probe_tail(&pdev, &isp) == setup[i].error);
		assert(read_pos == 15 && !strcmp(lifetime, setup[i].trace));
		count++;
	}
	printf("PASS %u AtomISP PCI snapshot and probe unwind cases; mocked hardware\n", count);
	return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-pci-save-") as temp:
    test = Path(temp) / "pci-save.c"
    binary = Path(temp) / "pci-save"
    test.write_text("\n".join([
        includes, *defs, saved_struct, translator, mock, snapshot,
        "static int probe_tail(struct pci_dev *pdev, struct atomisp_device *isp)\n{\n\tint err;",
        probe, cases,
    ]))
    cc = shlex.split(os.getenv("CC", "cc"))
    # Some cleanup labels also serve callers before the extracted probe tail.
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-label",
                    "-O2", str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
