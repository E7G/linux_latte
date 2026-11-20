# Mi Pad 2: live V4L2 latency during initial CAPS

Board test: Mi Pad 2 front OV5693 through AtomISP on
`7.2.15-mipad2-integrated-lpat10`. This source patch is for the
GStreamer 1.28.7 V4L2 userspace plugin, not the kernel or firmware.

## Fault and change

A live capture can push fixed CAPS and trigger an encoder's first upstream
LATENCY query before V4L2 allocation has applied the format to the device.
The installed 1.28.7 source rejects the query because the device FPS is
still zero. Observers on both sides of VPP and the capture queue show
the request reaches the source. After device format application the same
path returns a live reply. By then the VA encoder has already selected
the non-live output depth of four buffers.

[`gstreamer-v4l2src-early-latency.patch`](gstreamer-v4l2src-early-latency.patch)
uses the fixed source CAPS framerate for the minimum frame (or alternate
field) duration in that startup window. It returns an unknown maximum
until the V4L2 pool is configured and leaves the established-device
calculation in place. The device-open guard is unchanged. No timestamps,
frame rates, buffer limits, VA settings, or launchers are rewritten.

## Reproduce and test the patch

Source: the
[official gst-plugins-good 1.28.7 archive](https://gstreamer.freedesktop.org/src/gst-plugins-good/gst-plugins-good-1.28.7.tar.xz),
SHA-256 `87256969c82cf3bc8574301f3e7044a90de0ac500a5a27d8ba38c4dde894dd8b`.
Apply from the extracted source root; use an isolated plugin directory
and a fresh registry when checking the `v4l2src` factory.

```sh
git apply --check /path/to/gstreamer-v4l2src-early-latency.patch
git apply /path/to/gstreamer-v4l2src-early-latency.patch
meson setup build --wrap-mode=nofallback --buildtype=release \
  -Dauto_features=disabled -Dv4l2=enabled -Dv4l2-libv4l2=enabled \
  -Dv4l2-gudev=disabled -Dexamples=disabled -Dtests=disabled \
  -Ddoc=disabled -Dnls=disabled
ninja -C build sys/v4l2/libgstvideo4linux2.so
```

Test artifact SHA-256:
`12e35a4aad03358763ff6520cdd834f90a0f081569cbc60bcae84e8ee02b35f8`.
Source archive and target plugin ABI differ from the build SDK minor
patch level: SDK 1.28.9, verified runtime 1.28.7.

On the tablet, the scoped pipeline was 1920×1440 linear YU12 DMA-BUF from
`v4l2src`, a two-slot non-leaky capture queue, VA VPP to NV12 VA memory,
and H.264 at 15 Mbit/s with no B-frames. The same private VA plugin and
CherryView i965 linear PRIME_2 import candidate were used across arms.
`GST_DEBUG=vah264enc:4` from that VA plugin reported the effective
live/queue settings. The timing observer did not map frames.

| Short arm (240 decoded frames each) | Effective live/depth | Measured fps | Max PTS gap |
|---|---|---:|---:|
| Installed V4L2 source, no query override | 0 / 4 | 28.903 | 54.000 ms |
| Installed source, early-CAPS query comparator | 1 / 0 | 22.602 | 56.000 ms |
| Installed source, early-CAPS query comparator | 1 / 2 | 29.355 | 66.333 ms |
| Patched V4L2 source, no query override | 1 / 2 | 29.013 | 53.667 ms |

The comparator validates the mechanism; it is not part of this patch.
The patched source fixed the live negotiation without the comparator.
All 240 source, encoder and decoded frames matched after natural EOS.
The unsplit 1800-packet run also reported live/depth 1/2 and decoded all
1800 frames with no adjacent repeats or duplicate PTS. It measured
28.398 fps, max PTS gap 574.667 ms. A missing DQBUF match prevented a
full per-stage join for this run; there is no stage attribution for that
long gap.
This does not qualify app-triggered stop, steady 30 fps, OEM image quality,
all camera modes, or installation as a system default.
