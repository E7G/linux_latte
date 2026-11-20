# Mi Pad 2 i965 linear PRIME_2 input

This source-only companion targets the
[i965-irql 2.4.5 reference](https://github.com/irql-notlessorequal/intel-vaapi-driver/tree/0b648be50cd80e16469c135c76ff61bbd2f2d12b).
It does not install a driver or change the kernel, camera launcher or image.

The baseline i965 import path can return success for a PRIME_2 descriptor
without importing the external object. An isolated system DMA heap test
received all-zero luma/chroma instead of the six known input colors, even
without AtomISP or a physical camera. On the actual camera, 60 pre-encode
VPP readbacks contained a single repeated black frame. The system-memory
control was correct and the baseline legacy PRIME path could read the
same payload on the GPU.

`candidate.patch` translates single-object, single-layer linear NV12,
I420 and YV12 PRIME_2 into the existing GEM PRIME import. Plane offsets,
pitches, modifier and object bounds must fit the existing representation.
An unsupported arrangement is rejected rather than silently returning
a fresh unrelated VA surface. The same synthetic DMA buffers then read
back the six exact Y values and both chroma values; real OV5693 pre-encode
readback yielded 60 distinct frames.

## Rebuild and check

```sh
# From this directory, point the test at an untouched checkout of the reference.
python3 test_layout.py /path/to/intel-vaapi-driver
python3 -O test_layout.py /path/to/intel-vaapi-driver
```

The test pins the stock and patched source plus the actual extracted
conversion function. It runs with UBSan and checks all three valid formats
and unsupported/malformed geometry. Requires Python, GNU patch, a C compiler
with UBSan and libva/libdrm development headers. No device is opened.
All 23 checks pass under both normal Python and `python3 -O`.

Apply `candidate.patch` at the pinned driver source root. The tested driver
used Meson release builds with `-Dwith_x11=no -Dwith_wayland_drm=no`.
Keep tests process-local with a private `LIBVA_DRIVERS_PATH`, and verify
factory selection and the test library digest before starting.

## 1920×1440 direct device qualification

On Mi Pad 2 LPAT10, the private combined driver adds only this PRIME_2
companion to the already published [GPU IDRT experiment](../i965-gpu-idrt/README.md).
Combined library SHA-256:
`a6925e5fdea73f9c45b90bc8f9b336efac792ea48c550c755030dda71c469053`.
Both arms used the same private library and patched V4L2 source, a two-slot
non-leaky pre-VPP capture queue, NV12 VA conversion and H.264 15 Mbit/s,
no B-frames and verified live depth 2. The only experiment flag changed
was `MP2_I965_GPU_MBENC_IDRT`. The power, geometry and bitrate settings
were not modified between arms.

| 1,800-frame run | GPU IDRT OFF | GPU IDRT ON |
|---|---:|---:|
| Decoded frames | 1800 | 1800 |
| PTS span | 63.309 s | 59.964 s |
| Measured fps | 28.416 | 30.002 |
| Maximum PTS gap | 71.334 ms | 34.000 ms |
| PTS gaps over 50 ms | 95 | 0 |
| Encoder `vaEndPicture` median | 32.379 ms | 30.459 ms |
| Enclosed i915 render-wait median | 17.828 ms | 10.203 ms |

There were no repeated adjacent decoded frames or duplicate PTS. All
1,800 frames joined across capture, conversion and encoder pads in each
arm. Terminal driver diagnostics confirmed 1,800 GPU descriptor uploads
and zero fallback on the ON run, with no GPU uploads in the OFF run.
This ordered pair qualifies the one-minute direct front-camera cadence
at this resolution under the measured conditions. It does not cover the
normal camera UI stop path, concurrent audio/preview, optically matched
OEM quality, long endurance, reverse order or post-resume recording.

A separate frame-indexed moving-ball input at the same resolution
produced 120 frames per arm. All decoded frame hashes and the complete
Annex B bitstream matched between modes, with terminal GPU upload counts
0/120. This controlled content check is not an optical quality claim.
