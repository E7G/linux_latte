# Mi Pad 2 7.2: crop-dependent frame intervals

LPAT11 implements capture `G_PARM`/`S_PARM` on both cameras but returns
`ENOTTY` from `VIDIOC_ENUM_FRAMEINTERVALS`. A single 30 fps value is
not a substitute for the sensor controls: the maximum changes
with crop, horizontal/vertical binning and sensor-specific margins.

The LPAT12 candidate uses the standard
[STEPWISE interval ABI](https://docs.kernel.org/userspace-api/media/v4l/vidioc-enum-frameintervals.html).
AtomISP negotiates the requested FourCC and geometry in TRY state,
passes the locked padded format and crop to the sensor, and gets an
exact range with one frame-length line per step. It returns `EINVAL`
for a non-zero index or if the requested format would have to be
adjusted. The ioctl does not select a sensor, set ACTIVE state, power
the hardware or program a frame interval. Existing discrete sensors
keep their previous callback. The range describes accepted timing
requests, not a measured promise about ISP or encoder throughput.

## GStreamer 1.28.7 compatibility

The unpatched probe expands each step into a GStreamer fraction list.
On the installed runtime, the 1920×1440 timing model overflows the
fraction arithmetic at the first or third entry; omitting the normal
30 fps requests from both lists is a compatibility regression.
Do not treat kernel-only testing as a desktop qualification.

`gstreamer-v4l2-atomisp-stepwise.patch` applies from the root of the
GStreamer 1.28.7 `gst-plugins-good` tarball, after the existing
`gstreamer-v4l2src-early-latency.patch`. It affects only AtomISP
stepwise probing. It reports a bounded range of accepted requests
to GStreamer instead of materializing thousands of line timings;
`S_PARM` still quantizes requests and reports the actual period.
Other V4L2 drivers and discrete/continuous enumeration stay unchanged.
This does not make GStreamer’s global caps describe a different frame
rate range for every size in its integer size range.

## Qualification

* Kernel host tests exercise 14,760 TRY crop/range combinations, format
  and index rejection, exact known 1080p timing, and independent sensor
  locking/geometry, current interval and exposure regressions.
* The GStreamer helper extracted from the patched source was checked
  with the tablet’s GStreamer runtime. For 1080p and 1920×1440 it
  accepts nominal 30 fps and the exact 30.002 fps front rate, rejects an
  out-of-range 120 fps, and handles malformed/equal interval endpoints.
* Full LPAT12 (`f6bc1261f71ca2732fd92f346324450a6021231b`) built
  with the LPAT11 config. All 37 module signatures and 55 bundle
  files verified. The expected release booted in the one-shot GRUB
  entry; the saved rollback entry was unchanged.
* On both inputs, 24 native enumerations matched the previous
  hardware control readback at 640×480, 1280×720, 1920×1080 and
  1920×1440 in NV12, YU12 and YUYV. 144 endpoint, step and clamp
  `S_PARM` round trips passed. While streaming, 120 concurrent
  queries per camera took place without changing ACTIVE state or
  interrupting the 150 ordered buffers on either input.
* The initial run's fixture compared exposure against a value read
  before restoring VBLANK, which can itself change exposure. After
  re-reading controls following VBLANK, the saved state was
  restored and the entire matrix passed again.
* On the same LPAT12 boot, stock GStreamer 1.28.7 failed all six
  fixed 30 fps tests with `not-negotiated`. The replacement plugin
  passed all six: both cameras, 1080p and 1920×1440, with nominal
  30/1 and the native front 78125/2604 request. It also passed the
  same six tests on LPAT11. The plugin was loaded from a private
  path/registry, with the same ELF dependencies as the stock build
  (including GUdev). No system plugin or package was overwritten.

Remaining deployment gate: distribute and roll back the compatible
backend together with the kernel. Booting LPAT12 with an unmodified
GStreamer 1.28.7 installation is a demonstrated regression; do not
make the kernel a daily default on its own. An original signed Arch
`gst-plugins-good 1.28.7-1` archive was verified and its V4L2 plugin
matched the installed file byte-for-byte for rollback.

## Guarded follow-up

The follow-up keeps exact interval reporting disabled by default for
the two sensors that supply it. The paired
[Arch package](packages/gst-plugins-good-mipad2/README.md) enables it
at boot only for the matching native backend. The package-manager hook
restores legacy probing before runtime replacement or rollback. In an
isolated ALPM installation, all 124 unchanged stock files matched byte
and mode checks, a deliberate gate write error aborted before replacement,
and downgrading recovered the signed stock plugin exactly. A simulated
future runtime update also left the feature disabled. The guarded
kernel object compiled and passed the host dispatch test.

Full LPAT13 from `2b23322aca9de940fd61c0f63f2354f87ec47a8b` built
and passed verification of all 37 module signatures and 55 bundle
files. In a networkless UEFI QEMU guest with the signed AtomISP
module and actual Arch systemd, pacman and GStreamer 1.28.7:

* The stock backend loaded with STEPWISE still off after user-session
  startup; the activation unit was absent.
* The paired backend loaded with the gate initially off and then
  enabled by the packaged unit before user sessions were allowed.
* The real ALPM downgrade ran the disarm hook before file changes,
  restored the stock plugin digest and passed its integrity check.
  A same-boot reinstall and service restart kept the gate off.
* LPAT11, which lacks this parameter, still loaded the paired plugin
  and completed the package downgrade and reinstall.

## Guarded LPAT16 on the Mi Pad 2

On 2026-11-21, signed 7.2.15 LPAT16 source
32d51fb913b685343cceba712794450b8c92a14a booted through a GRUB one-shot
with the saved fallback preserved. Both cameras were tested on the
same physical boot with the stock and paired native plugins.

* With the stock Arch backend, the switch stayed off, all 24 queries
  returned the original ENOTTY, and all 144 frame-period round trips
  passed. Six native GStreamer 30 fps and exact front-rate requests
  reached EOS at 1920x1080 and 1920x1440.
* With the paired package installed by pacman under the existing policy,
  the packaged systemd service enabled the gate. All 24 enumerations
  matched the hardware readbacks. Both cameras completed 120 concurrent
  queries while delivering 150 ordered frames each. The same six native
  GStreamer cases passed.
* The physical ALPM downgrade disarmed the gate and restored the
  signed stock package, including all 224 managed files and the
  original plugin digest. Reinstalling and restarting the service on
  that boot left the gate off. The final package and gate were stock.
* An RTC trial accumulated 19,088,224 us of S0i3 residency on that same
  boot. Both cameras then delivered 240 ordered 1920x1080 NV12 frames
  at approximately 30 fps. Backlight and saved camera state recovered.

The early activation sequence was exercised in the VM and the real
packaged activation, capture and rollback were exercised on the tablet.
