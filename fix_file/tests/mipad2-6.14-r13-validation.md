# Mi Pad 2 r13: measured warm-mode/max-size fixes; tiny front capture still fails

Measured 2026-10-12. Built source `0be81e7c6da1fe7c1e00be5c92dcdd2db15908b2`, current r13
boot `d5b11c82-7a51-40d3-acd0-1c67bd1ca9c6`. Saved default bqdiag1 remains unchanged.
Only the following scoped evidence is claimed; full support remains incomplete.

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

## Hardware follow-up

Full LLVM21 ThinLTO W=1 build exit0, source/HEAD and protected r12 artifacts
unchanged.34 CMS module signatures verified. Isolated stage, normal-initrd
hash persistence/unchanged check, earlyserial unit verify and GRUB raw Btrfs
byte comparisons passed. App r12 after-scaling window had not passed preview
gate; it was gracefully quit (MainPID0/Resultsuccess/ExecMainStatus0), not
counted as a streaming preview closure. One-shot r13 reached SSH/COM17;
saved_entry=bqdiag1, next_entry consumed. Initial hardware smoke passed.

-3,876 original strict/cadence/oversized capture frames passed. Both sensors
  owner isolation, surviving-fd takeover, ordinary STREAMOFF/ON, streamparm,
  30/15fps within1%, CREATE_BUFS size contract and full1MiB sentinel tails.
  New cadence gate additionally queries enum during streaming and verifies
  video/sensor ACTIVE FORMAT and exposure/VBLANK/gain/R/B preservation.
  This does not separately prove crop-left/top preservation inside every
  query; outer crop/format/controls restored exactly. Do not overstate scope.
- Front forced-powered warm-mode reproduction now reports/physically outputs
  1296x976 then1296x736,48frames each. The r12 stale976-row failure is fixed
  in this run; temporary power policy restored, read-only register sampling.
- Seven-format matrix on both sensors:13/14 cases pass48frames/four phases
  within1% at30fps (624 positive frames). Extreme16384x16384 now negotiates
  1920x1440 and captures on both; front1920x1200 and1280x720 rapid switches
  also pass. Full matrix still FAILS: front1x1->4x4 produces no frame then
  timeout. Rear4x4 passes. Do not omit or redefine this failed gate.
- Real non-stream v4l2-compliance improves72/74 to74/74, exit0 on both runs
  across both inputs. TWO missing ENUM_FRAMEINTERVALS warnings remain.
  This green metadata test does NOT prove the advertised tiny front sizes
  stream, or full streaming compliance. Real capture contradicts that claim.

## Retained additional tiny-input evidence, not a production repair

Front tiny-size sweep:4/8/16 square and4/8/16-wide x32 fail without frames;
24/32/64 square and32-wide x4/8/16 pass48frames. Thus width, not merely tiny
height, is implicated; no absolute hardware minimum is asserted from this.

Using existing writable pad_w module parameter temporarily, preserve logical
4x4 output while changing sensor input width. Widths20/28/32/34 and38 fail;
36/40/44/52 pass48frames. All tests restore pad_w16 plus sensor state. This
suggests a small-input/alignment constraint, but does not distinguish sensor
ROI/bin origin, packed RAW transport and ISP constraints as the causal layer.

A further temporary policy (input at least36 and aligned4, without changing
logical output) passes ten18..1302-wide x32 cases,48frames each, including
two-pixel steps and binning-boundary neighbors. Cropped output remains exactly
requested. This is480 diagnostic frames, NOT a permanent r13 kernel fix.
Next source should preserve full logical range by correcting input geometry,
not just hide the4x4 failure by arbitrarily raising the output minimum.
Untested breadth/quality/crop-phase/pixel integrity still needs verification.

## Resume/audio/user checks

Cold/post-resume silent hardware DAC_REF/RT5659/TFA active-idle checks pass,
no mixer/cache repair. Two10-second RTC runs return same boot; first PMC
S0I3 after9428224us, second independently measured delta9203456us with normal
debug settings, restored. No BUG/WARNING/UBSAN/CallTrace in electrical audit;
expected diagnostic CSS timeout/queued-buffer warnings retained separately.

User earlier declined listening (temporarily inconvenient): NO r13 audible
tones played, acoustic confirmation null. R13 desktop app preview, photos,
recording/GUI close not yet confirmed; r11/r12 checks not reused as proof.
Full interval enumeration/AWB/3A/streaming/other hardware support stays open.
