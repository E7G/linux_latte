#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Try the actual lane routine and S_FMT entry against faultable PCI access."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

root = Path(os.getenv("MIPAD2_KERNEL_SOURCE", str(Path(__file__).resolve().parents[2])))
driver = root / "drivers/staging/media/atomisp/pci"
v4l2 = (driver / "atomisp_v4l2.c").read_text()
cmd = (driver / "atomisp_cmd.c").read_text()
regs = (driver / "atomisp-regs.h").read_text()
pci = (root / "include/linux/pci.h").read_text()
lane = v4l2[v4l2.index("int atomisp_csi_lane_config("):
            v4l2.index("static int atomisp_subdev_probe(")]
fmt = cmd[cmd.index("int atomisp_set_fmt("):cmd.index("int atomisp_set_shading_table(")]
first_active_write = "pipe->sh_fmt = format_bridge->sh_fmt;"
# The real S_FMT prefix includes TRY, lane programming and the first ACTIVE write.
# The rest of the unchanged camera programming is outside this fixture's scope.
fmt_entry = fmt[:fmt.index(first_active_write) + len(first_active_write)] + "\nreturn 0;\n}"
if fmt.count("atomisp_csi_lane_config(isp)") != 1:
    raise SystemExit("S_FMT must handle exactly one CSI lane configuration")
pci_errors = re.findall(r"^#define PCIBIOS_[A-Z_]+[^\n]*", pci, re.M)
converter = pci[pci.index("static inline int pcibios_err_to_errno("):
                pci.index("/* Low-level architecture-dependent routines */")]
registers = re.findall(
    r"^#define (?:MRFLD_PCI_CSI_CONTROL|MRFLD_PORT_CONFIG[^ \t]*|MRFLD_PORT[123]_[A-Z_]+|CHV_PORT[A-Z0-9_]+)[ \t]+[^\n]*",
    regs, re.M)

mock = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef uint8_t u8;
typedef uint32_t u32;
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define N_MIPI_PORT_ID 3
#define ATOMISP_HW_REVISION_ISP2401_LEGACY 2
#define ATOMISP_HW_REVISION_ISP2401 3
#define ATOMISP_HW_REVISION_SHIFT 8
#define PCI_POSSIBLE_ERROR(val) ((val) == UINT32_MAX)
#define dev_err(...) do { } while (0)
#define dev_dbg(...) do { } while (0)

struct pci_dev { int reserved; };
struct atomisp_sub_device { int reserved; };
struct atomisp_video_pipe { struct atomisp_sub_device *asd; int sh_fmt; };
struct atomisp_device {
	struct pci_dev *dev;
	struct { unsigned int hw_revision; } media_dev;
	int sensor_lanes[3];
};
struct video_device { struct atomisp_device *isp; struct atomisp_video_pipe *pipe; };
struct atomisp_format_bridge { int sh_fmt; };
struct v4l2_format { struct { struct v4l2_pix_format { int reserved; } pix; } fmt; };
struct ia_css_frame_info { int reserved; };
struct v4l2_mbus_framefmt { int reserved; };
struct v4l2_rect { int reserved; };

static int reads, writes, tries, pipe_error, try_error, read_error, write_error;
static u32 before, written;
static struct pci_dev *to_pci_dev(struct pci_dev *dev) { return dev; }
static struct atomisp_device *video_get_drvdata(struct video_device *dev) { return dev->isp; }
static struct atomisp_video_pipe *atomisp_to_video_pipe(struct video_device *dev) { return dev->pipe; }
static int atomisp_pipe_check(struct atomisp_video_pipe *pipe, bool check)
{
	assert(pipe && check);
	return pipe_error;
}
static int atomisp_try_fmt(struct atomisp_device *isp, struct v4l2_pix_format *pix,
			   const struct atomisp_format_bridge **fmt,
			   const struct atomisp_format_bridge **sensor_fmt)
{
	static const struct atomisp_format_bridge bridge = { 127 };

	assert(isp && pix);
	tries++;
	*fmt = *sensor_fmt = &bridge;
	return try_error;
}
static int pci_read_config_dword(struct pci_dev *dev, int offset, u32 *value)
{
	assert(dev && offset == MRFLD_PCI_CSI_CONTROL);
	reads++;
	*value = read_error ? UINT32_MAX : before;
	return read_error;
}
static int pci_write_config_dword(struct pci_dev *dev, int offset, u32 value)
{
	assert(dev && offset == MRFLD_PCI_CSI_CONTROL && reads == 1);
	writes++;
	written = value;
	return write_error;
}
"""

cases = r"""
/* Reference packed fields for each approved topology, independent of driver arithmetic. */
static const struct row { int x, y, z; u32 legacy, chv; } golden[] = {
	{ 4, 1, 0, 0xfc, 0xfc },
	{ 3, 1, 0, 0x100bc, 0x100bc },
	{ 2, 1, 0, 0x2009c, 0x2009c },
	{ 1, 1, 0, 0x3008c, 0x3008c },
	{ 2, 1, 2, 0x40398, 0x40698 },
	{ 3, 1, 1, 0x801b8, 0x802b8 },
	{ 2, 1, 1, 0x90198, 0x90298 },
	{ 1, 1, 1, 0xa0188, 0xa0288 },
	{ 4, 2, 0, 0x1001fc, 0x1001fc },
	{ 3, 2, 0, 0x1101bc, 0x1101bc },
	{ 2, 2, 0, 0x12019c, 0x12019c },
	{ 1, 2, 0, 0x13018c, 0x13018c },
	{ 2, 2, 2, 0x140398, 0x140798 },
	{ 3, 2, 1, 0x1801b8, 0x1803b8 },
	{ 2, 2, 1, 0x190198, 0x190398 },
	{ 1, 2, 1, 0x1a0188, 0x1a0388 },
};

static const struct row *expected(int hw, int x, int y, int z)
{
	for (int i = 0; i < (hw == 3 ? 16 : 8); i++)
		if ((!x || x == golden[i].x) && (!y || y == golden[i].y) &&
		    (!z || z == golden[i].z))
			return &golden[i];
	return NULL;
}

int main(void)
{
	const struct fault { int read, write, ret, writes; u32 before; } faults[] = {
		{ 0, 0, 0, 1, 0xa5a5a5a5 },
		{ 0, 0, 0, 1, 0x02001000 },
		{ PCIBIOS_DEVICE_NOT_FOUND, 0, -ENODEV, 0, 0 },
		{ -ETIMEDOUT, 0, -ETIMEDOUT, 0, 0 },
		{ 0, 0, -ENODEV, 0, UINT32_MAX },
		{ 0, PCIBIOS_SET_FAILED, -EIO, 1, 0x5a5a5a5a },
		{ 0, PCIBIOS_BAD_REGISTER_NUMBER, -EFAULT, 1, 0x5a5a5a5a },
	};
	struct pci_dev pci = { 0 };
	struct atomisp_device isp = { .dev = &pci };
	struct atomisp_sub_device asd = { 0 };
	struct atomisp_video_pipe pipe = { .asd = &asd };
	struct video_device video = { .isp = &isp, .pipe = &pipe };
	struct v4l2_format fmt = { 0 };
	unsigned int cases = 0;

	for (int hw = 1; hw <= 3; hw++)
	for (int x = -1; x <= 5; x++)
	for (int y = -1; y <= 3; y++)
	for (int z = -1; z <= 3; z++)
	for (unsigned int i = 0; i < ARRAY_SIZE(faults); i++) {
		const struct row *row = expected(hw, x, y, z);
		const struct fault *f = &faults[i];
		u32 mask = hw == 1 ? 0x000f03ff : 0x001f07ff;
		int ret = row ? f->ret : -EINVAL;

		isp.media_dev.hw_revision = hw << 8;
		isp.sensor_lanes[0] = x;
		isp.sensor_lanes[1] = y;
		isp.sensor_lanes[2] = z;
		reads = writes = tries = 0;
		written = 0;
		read_error = f->read;
		write_error = f->write;
		before = f->before;
		pipe.sh_fmt = 204;
		assert(atomisp_set_fmt(&video, &fmt) == ret);
		assert(tries == 1 && reads == !!row);
		assert(writes == (row ? f->writes : 0));
		assert(pipe.sh_fmt == (ret ? 204 : 127));
		if (writes)
			assert(written == ((before & ~mask) | (hw == 1 ? row->legacy : row->chv)));
		cases++;
	}
	reads = writes = tries = 0;
	pipe.sh_fmt = 204;
	pipe_error = -EBUSY;
	assert(atomisp_set_fmt(&video, &fmt) == -EBUSY);
	assert(!reads && !writes && !tries && pipe.sh_fmt == 204);
	pipe_error = 0;
	try_error = -EINVAL;
	assert(atomisp_set_fmt(&video, &fmt) == -EINVAL);
	assert(!reads && !writes && tries == 1 && pipe.sh_fmt == 204);
	printf("PASS %u lane configurations and 2 S_FMT early error checks\n", cases);
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-atomisp-lane-") as temp:
    unit = Path(temp) / "test.c"
    binary = Path(temp) / "test"
    unit.write_text("#include <errno.h>\n" + "\n".join(pci_errors + registers) +
                    "\n" + converter + mock + lane + fmt_entry + cases)
    cc = shlex.split(os.environ.get("CC", "gcc"))
    for level in ("-O0", "-O2"):
        subprocess.run(cc + [level, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                             "-Wno-unused-variable", "-Wno-sign-compare", "-fsanitize=undefined",
                             "-fno-sanitize-recover=all", str(unit), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
