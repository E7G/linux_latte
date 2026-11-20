#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the actual CSI_READY read/modify/write with faultable PCI I/O."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

root = Path(os.getenv("MIPAD2_KERNEL_SOURCE", str(Path(__file__).resolve().parents[2])))
atomisp = root / "drivers/staging/media/atomisp"
source = (atomisp / "pci/atomisp_cmd.c").read_text()
regs = (atomisp / "pci/atomisp-regs.h").read_text()
revision = (atomisp / "include/linux/atomisp.h").read_text()
pci = (root / "include/linux/pci.h").read_text()
helper = re.search(r"^int atomisp_csi_set_ready\([^;{}]*\)\n\{.*?^\}", source, re.M | re.S)
if helper is None:
    raise SystemExit("Missing AtomISP CSI_READY helper")
converter = re.search(r"^static inline int pcibios_err_to_errno\(.*?^\}", pci, re.M | re.S).group()

defs = []
for header, names in (
    (regs, r"MRFLD_PCI_CSI_CONTROL(?:_CSI_READY)?"),
    (revision, r"ATOMISP_HW_(?:REVISION_(?:ISP2401|SHIFT)|STEPPING_B0)"),
    (pci, r"PCIBIOS_[A-Z_]+|PCI_ERROR_RESPONSE|PCI_POSSIBLE_ERROR\(val\)"),
):
    defs += re.findall(rf"^#define (?:{names})[ \t]+[^\n]+", header, re.M)

mock = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define BIT(n) (1UL << (n))
#define lockdep_assert_held(m) assert(*(m))
#define to_pci_dev(d) (d)

struct pci_dev { u32 control; };
struct atomisp_device {
	struct pci_dev *dev;
	struct { unsigned int hw_revision; } media_dev;
	bool mutex;
};

static int reads, writes, read_error, write_error;

static int pci_read_config_dword(struct pci_dev *dev, int offset, u32 *control)
{
	assert(dev && offset == 0xe8);
	reads++;
	*control = dev->control;
	return read_error;
}

static int pci_write_config_dword(struct pci_dev *dev, int offset, u32 control)
{
	assert(dev && offset == 0xe8 && reads == 1);
	writes++;
	if (!write_error)
		dev->control = control;
	return write_error;
}
"""

cases = r"""
#define READY_MASK UINT32_C(0x02000000)
_Static_assert(MRFLD_PCI_CSI_CONTROL_CSI_READY == READY_MASK, "CSI_READY must be bit 25");
_Static_assert(MRFLD_PCI_CSI_CONTROL == 0xe8, "Wrong CSI register");

static void check(unsigned int revision, bool enable, u32 before, int read_status,
		  int write_status, int expected_error, int expected_reads,
		  int expected_writes, u32 expected)
{
	struct pci_dev pci = { .control = before };
	struct atomisp_device isp = {
		.dev = &pci,
		.media_dev = { .hw_revision = revision },
		.mutex = true,
	};

	read_error = read_status;
	write_error = write_status;
	reads = writes = 0;
	assert(atomisp_csi_set_ready(&isp, enable) == expected_error);
	assert(reads == expected_reads && writes == expected_writes);
	assert(pci.control == expected && "update exactly bit 25, preserve live lane bits");
}

int main(void)
{
	const unsigned int b0 = 0x2010;
	const u32 values[] = { 0, 1, 0xa1a5dead, 0xf5ffffff };
	unsigned int count = 0;

	/* Use independent register values and verify both transitions and no-ops. */
	for (unsigned int i = 0; i < sizeof(values) / sizeof(values[0]); i++) {
		for (unsigned int revision = b0 - 1; revision <= b0 + 1; revision++) {
			for (unsigned int ready = 0; ready < 2; ready++) {
				u32 before = values[i] | (ready ? READY_MASK : 0);

				for (unsigned int enable = 0; enable < 2; enable++) {
					u32 after = enable ? before | READY_MASK : before & ~READY_MASK;
					bool supported = revision >= b0;

					check(revision, enable, before, 0, 0, 0, supported,
					      supported && after != before, supported ? after : before);
					count++;
				}
			}
		}
	}
	check(b0, true, 0, PCIBIOS_DEVICE_NOT_FOUND, 0, -ENODEV, 1, 0, 0);
	check(b0, false, READY_MASK, PCIBIOS_BAD_REGISTER_NUMBER, 0, -EFAULT, 1, 0, READY_MASK);
	check(b0, true, UINT32_MAX, 0, 0, -ENODEV, 1, 0, UINT32_MAX);
	check(b0, false, UINT32_MAX, 0, 0, -ENODEV, 1, 0, UINT32_MAX);
	check(b0, true, 0, 0, PCIBIOS_SET_FAILED, -EIO, 1, 1, 0);
	check(b0, false, READY_MASK, 0, -ETIMEDOUT, -ETIMEDOUT, 1, 1, READY_MASK);
	check(b0 - 1, true, UINT32_MAX, PCIBIOS_DEVICE_NOT_FOUND, 0, 0, 0, 0, UINT32_MAX);
	printf("PASS %u extracted AtomISP CSI_READY register/error/stepping cases; mocked PCI\n",
	       count + 7);
	return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-csi-ready-") as tmp:
    test = Path(tmp) / "ready.c"
    binary = Path(tmp) / "ready"
    test.write_text("\n".join([mock, *defs, converter, helper.group(), cases]))
    cc = shlex.split(os.getenv("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
