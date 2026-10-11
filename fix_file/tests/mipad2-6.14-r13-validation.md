# Mi Pad 2 r13 preview/warm-mode candidate — NOT device validated

Prepared 2026-10-12. Tablet remains r12, stable saved default bqdiag1.
Source-pinned build/manifest will identify the final candidate commit. These
source changes have not been booted; no r13 camera/compliance/audio PASS.

## Production changes

1. Backport upstream preview1920x1440 request limit, from Linux commit
   [1d2e5bef1315fe5d92cb087beaba5d7b2c8d2cff](https://github.com/torvalds/linux/commit/1d2e5bef1315fe5d92cb087beaba5d7b2c8d2cff).
   This limits height before sensor TRY_FMT, not merely after unsupported
   geometry has already reached CSS. Other run modes keep existing limits.
2. OV5693 applies mode crop/output/binning registers on every STREAMON,
   before replaying cached controls and enabling streaming. Runtime resume
   alone is insufficient when the sensor remains powered across S_FMT.
   Mode/control/stream-on errors propagate and release the acquired runtime
   PM reference with an idle-capable put, not a no-idle-only decrement.
3. Crop-capable frame-size enumeration becomes a stepwise range derived
   from the SAME TRY_FMT negotiation, rather than a discrete preferred-size
   list which omitted supported cropped sizes. Index0 only, alignment2,
   min/max and errors propagated. No ACTIVE sensor/control mutation intended.
   Non-crop sensor enumeration path is unchanged. See
   [V4L2 frame-size contract](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-enum-framesizes.html).

## Authoritative r12 negative baselines

Existing r12 extreme-size requests16384x16384 return TRY_FMT1920x1944/front,
1920x2460/rear, then S_FMT fails firmware binary selection. Explicit
1920x1440 captures48 strict frames on BOTH sensors, supporting the proposed
upper preview geometry, not proving all dimensions in the future range.

A seven-format r12 sweep additionally exposed front partial/zero-frame
timeouts after rapid changes. A targeted reproduction held the front sensor
runtime power on, without raw sensor-register writes. First1280x960 request
reported/physically output1296x976 and captured48 frames. Next1280x720
reported1296x736 but live read-only0x3808/0x380a still read1296x976; only one
frame then timeout. HTS2688/VTS1984 and powered-active state were sampled
while the capture process was live. Runtime power policy and crop/format/
sampled controls restored exactly. This directly proves stale hardware mode
under retained power, not a complete explanation of every old black preview.
Adjacent baseline summaries retain failures; original raw logs remain local.

## Offline gates

Real extracted source functions passed ASan/UBSan/Werror:36,864 OV5693
mode/control/stream/PM-reference cases and102,054 preview/range negotiation
cases. Old-code in-memory negative fixtures compile then fail assertions,
showing both defects are caught. CCI, PM, sensor negotiation/format/padding
remain stubs: not proof of actual I2C, locks, DMA or firmware selection.
Seven previous queue/CSS/interval/sequence/multiopen/streamparm suites pass.
Three-driver diff checkpatch0 errors/warnings/checks. New60-frame enum/cadence
and12-frame-per-phase format probes compile with Wall/Wextra/Werror, UNRUN.

## Required real next gates

- Full real kernel-header compile/link/modules, protected r12 hashes,34 CMS
  signatures, isolated stage/initrd/GRUB byte verification, one-shot only.
- Keep original strict queue/streamparm/cadence/CREATE_BUFS/tail gates.
- Warm OV5693 two-mode reproduction must now report matching live registers
  AND return all48 frames on each mode while runtime power stays on.
- Both sensors:1x1 and16384x16384 negotiation plus1920x1440,1920x1200,
  1280x960,1280x720,720x1280 actual capture/restart/takeover. Preserve existing
  negative diagnostics rather than hiding failing matrix cases.
- Query the stepwise enum during streaming and verify ACTIVE video/sensor
  formats, VBLANK/exposure/gain/R/B controls unchanged, index1/invalid format
  rejected. Measure native/app caps negotiation after enumeration model change.
- Real no-stream AND appropriate streaming compliance; don't replace with
  host success. Interval enumeration remains unsupported in this candidate.
- RTC/S0I3, audio electrical and user hearing when convenient, Snapshot
  preview/real quit, both camera photos/recording/GUI close as applicable.

Full AWB/3A, interval enumeration, complete streaming compliance, exhaustive
power/app/hardware validation remain open. R12 user declined listening for
now; no r12/r13 tones have been played and no acoustic success is claimed.
