#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply the pinned patch and compile its real PRIME_2 layout helper."""
from hashlib import sha256
from pathlib import Path
import argparse
import os
import shlex
import subprocess
import tempfile


BASE = '7c6df216e10c50a36d611de625bb6e2223ed5179a93414c07b48193183657354'
PATCHED = 'a4f6af3151a3975aea08682ae396afbcc92d879a2adcf182e659ca050094cee2'
HEADER = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <va/va.h>
#include <va/va_drmcommon.h>
#include <drm_fourcc.h>
'''
TEST = r'''
enum { W = 1920, H = 1440, Y = W * H, SIZE = Y * 3 / 2 };
static unsigned tests;

static void check(int valid, const char *test)
{
    if (!valid) {
        fprintf(stderr, "%s failed\n", test);
        exit(1);
    }
    tests++;
}

static VADRMPRIMESurfaceDescriptor layout(uint32_t va, uint32_t drm, int planar)
{
    VADRMPRIMESurfaceDescriptor d = {
        .fourcc = va, .width = W, .height = H, .num_objects = 1,
        .objects = {{ .fd = 7, .size = SIZE, .drm_format_modifier = DRM_FORMAT_MOD_LINEAR }},
        .num_layers = 1,
        .layers = {{ .drm_format = drm, .num_planes = planar ? 3 : 2,
                     .offset = {0, Y, Y + Y / 4},
                     .pitch = {W, planar ? W / 2 : W, W / 2} }},
    };
    return d;
}

int main(void)
{
    VASurfaceAttribExternalBuffers out;
    uintptr_t fd;
    const uint32_t va[] = {VA_FOURCC_NV12, VA_FOURCC_I420, VA_FOURCC_YV12};
    const uint32_t drm[] = {DRM_FORMAT_NV12, DRM_FORMAT_YUV420, DRM_FORMAT_YVU420};
    for (unsigned i = 0; i < 3; i++) {
        VADRMPRIMESurfaceDescriptor d = layout(va[i], drm[i], i != 0);
        check(i965_prime2_to_external(&d, W, H, &out, &fd) == VA_STATUS_SUCCESS, "valid");
        check(out.pixel_format == va[i] && out.width == W && out.height == H && fd == 7 &&
              out.buffers == &fd && out.num_buffers == 1 && out.data_size == SIZE &&
              out.num_planes == d.layers[0].num_planes, "legacy descriptor fields");
        for (unsigned j = 0; j < out.num_planes; j++)
            check(out.pitches[j] == d.layers[0].pitch[j] &&
                  out.offsets[j] == d.layers[0].offset[j], "legacy plane geometry");
    }
    VADRMPRIMESurfaceDescriptor good = layout(VA_FOURCC_I420, DRM_FORMAT_YUV420, 1);
    VADRMPRIMESurfaceDescriptor d = good;
#define REJECT(name, mutation, status) do {                                       \
    d = good; mutation;                                                           \
    check(i965_prime2_to_external(&d, W, H, &out, &fd) == (status), (name));        \
} while (0)
    REJECT("alternate modifier", d.objects[0].drm_format_modifier = I915_FORMAT_MOD_Y_TILED,
           VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE);
    REJECT("distinct objects", d.num_objects = 2, VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE);
    REJECT("different layer format", d.layers[0].drm_format = DRM_FORMAT_NV12,
           VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE);
    REJECT("stride mismatch", d.layers[0].pitch[2] += 16, VA_STATUS_ERROR_UNSUPPORTED_MEMORY_TYPE);
    REJECT("bottom padding outside the object", d.objects[0].size--, VA_STATUS_ERROR_INVALID_PARAMETER);
    REJECT("overlapping planes", d.layers[0].offset[2] = Y, VA_STATUS_ERROR_INVALID_PARAMETER);
    REJECT("wrong plane object index", d.layers[0].object_index[2] = 1,
           VA_STATUS_ERROR_INVALID_PARAMETER);
    REJECT("file descriptor not available", d.objects[0].fd = -1, VA_STATUS_ERROR_INVALID_PARAMETER);
    REJECT("input dimensions do not match request", d.width = W + 2, VA_STATUS_ERROR_INVALID_PARAMETER);
    printf("%u actual PRIME_2 helper checks passed\n", tests);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root', type=Path)
    args = parser.parse_args()
    raw = (args.source_root / 'src/i965_drv_video.c').read_bytes()
    if sha256(raw).hexdigest() != BASE:
        raise ValueError('Expected the i965 2.4.5 file from the pinned reference commit')
    patch = Path(__file__).resolve().with_name('candidate.patch')
    with tempfile.TemporaryDirectory(prefix='i965-prime2-layout-') as tmp:
        root = Path(tmp)
        source = root / 'src/i965_drv_video.c'
        source.parent.mkdir()
        source.write_bytes(raw)
        subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)],
                       cwd=root, check=True)
        patched = source.read_bytes()
        if sha256(patched).hexdigest() != PATCHED:
            raise ValueError('Patch output differs from the hardware-qualified source')
        text = patched.decode()
        start = text.index('static VAStatus\ni965_prime2_to_external(')
        end = text.index('static VAStatus\ni965_CreateSurfaces2(', start)
        unit = root / 'layout.c'
        unit.write_text(HEADER + text[start:end] + TEST, encoding='utf-8')
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'libdrm', 'libva'], text=True))
        test = root / 'check-layout'
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
                        *flags, str(unit), '-o', str(test)], check=True)
        subprocess.run([str(test)], check=True)


if __name__ == '__main__':
    main()
