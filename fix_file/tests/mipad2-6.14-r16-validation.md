# R16 — real default/minimum and both-start compliance gains; NOT complete

2026-10-12. R16 built source214a29ba23ac45397abbbc51348407e74264c5ee is
running, bootbb66609d-07c0-466c-bce1-9067b13617c9. Stable savedbqdiag1,
nextempty; one-shot only, no default promotion. Full objective remainsactive.
Hashes and explicit remaining requirements are in the adjacent summary.

## Physical evidence used, including retained failures

R15 six-shape,42-case front VBLANK matrix, unchanged48-frame strict fixture:
- 4x4 and640x480:8 fails;12/14/16/20/24/32 produce48 frames each.
- 1280x720 and1280x960:8/12 fail;14/16/20/24/32 produce48 frames each.
- 1298x720 and1920x1440:8/12/14/16/20 fail;24/32 produce48 frames each.

Read-only live registers identify both-axis binning0x31/0x31 versus no
binning0x11/0x11.42cases =26 streaming successes/1248 captured frames and
16 retained zero-frame failures. Video format/input/period plus BOTH sensor
formats/crops/controls restored exactly. This is not a proof of every shape,
mixed-binning mode, exact physical boundary, sustained stability or rate.
Especially tiny crops report over1000fps but deliver roughly650, and large
1920x1440 atVBLANK24 reports40.219fps but delivers about27.35. These source/
delivered timing disagreements REMAIN; no enum list fabricated to hide them.

Previous live stalled-state trace proves actual blocked input0/OV5693,
regardless of stdout's lastinput1 heading. At1280x720 VBLANK4 failed with
2 AND8 buffers;16/64 or explicit30 restored frame checks in both pools.

## Candidate changes

1. MiPad2-only tested guard bands:16 lines when BOTH X/Y binning are enabled,
   24 otherwise. Generic boards retain their historical4-line policy. These
   are guarded working boundaries, NOT asserted exact silicon minima. Mixed
   modes receive the more conservative guard and still need real testing.
2. MiPad2's S_FMT default uses the Android30fps baseline (HTS2688,VTS1984),
   rather than selecting the highest30fps multiple merely from crop height.
   Explicit faster intervals remain supported above the mode's blanking
   floor; no global30/60fps ceiling introduced. This fixes invalid advertised
   blanking/default policy in source, not all high-rate source/delivery
   mismatches. Do not claim physical120fps from arithmetic-only tests.
3. Atomisp crop/format helper returns a sensor error after unlocking BEFORE
   calling CSI set_fmt. Previously a successful CSI call masked the sensor
   failure and published the wrong success. Caller output remains unchanged
   on errors. This does NOT roll back all sensor ACTIVE state or prove real
   I2C/PM fault handling; full transaction/locking audit remains open.

The Android pinned micam/OV5693 mode table and exposure implementation give
a working30fps baseline, not universal arbitrary-crop limits. OmniVision's
preliminary OV5693 specification provides distinct full/binned readout
timelines and timing registers; it does not prove these board guard values.
Windows CPF/AIQB remain binary tuning data, not open3A algorithm source.

## Offline verification only

Thirteen actual-source-extracted host suites pass. New40000 sensor/crop/CSI
fault-return/lock cases,7824 timing-policy cases,11700 crop edge cases cover
board scoping/generic parity, defaults, guard choice and errno propagation.
Four intentionally regressed sources compile then fail assertions. Updated
geometry/OV fixtures include the new board field/helper. Generic old-default
parity stays asserted; MiPad2 intentionally changed-default expectations now
assert AndroidVTS1984. An initial high-rate model assertion forgot blanking
overhead atheight480; corrected its claim to the mathematically supported
small-height domain, without changing device tests or hiding timing failures.
ActualW=1 driver/header objects compile, checkpatchclean. These are models
and compilation, NOT R16 PM/DMA/IRQ/streaming/3A proof.

Next gate: full pinned R16 build/signatures/protected staging/one-shot boot;
test all defaults and new actual min-blank boundaries on tiny/binning/unbinned/
mixed/direct-subdev/large shapes, high-rate preservation, bothinput streaming
compliance, GUI/photo/recording and full regression. If a board guard breaks
valid fast modes or still exposes no-frame boundaries, revise it from evidence
rather than accept a smaller success definition. Earlier R15 negatives remain
retained. Full interval enum,3A/AWB, compat32/MediaRequests, control-error
rollback, broader hardware andflash-toolsintegration all remain open.

Primary references:
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/ov5693.h
- https://www.kernel.org/doc/html/latest/userspace-api/media/drivers/camera-sensor.html
- https://cdck-file-uploads-global.s3.dualstack.us-west-2.amazonaws.com/nvidia/original/2X/0/0ba1de548fe37ca20841d0a09bcb767f73fa9b16.pdf
- https://raw.githubusercontent.com/torvalds/linux/master/drivers/staging/media/atomisp/pci/atomisp_cmd.c

## R16 actual build / boot / scoped hardware evidence

Full isolated LLVM21 ThinLTO W=1 bzImage/modules targets observedexit0;
all command exits persisted,18 source hashes/HEAD unchanged and five R15
build artifacts protected.34 CMS module signatures verified, embedded config/
release/inventory checked. Protected staging kept stableboot/modules/app and
normalinitrd unchanged. Serialinitrd unitverify0 and rawGRUB/Btrfs kernel/
initrd byte comparisons pass. Onlycustom.cfg appended; savedbqdiag1 retained,
nextentry consumed once. SSH and COM17 returned on R16.

- **BOTH sensors13 default formats each** without S_PARM or exposure override:
  26cases×240=6240 frames, four phases each, all1%30fps/payload/typedmetadata/
  owner/restart/takeover/crop/controls assertions pass. Previous zero-frame
  default front formats now stream. No “high-exposure workaround” used.
- **13 front actual-advertised-minimum cases**:3120frames pass same frame/ABI
  checks. Query ranges match actual both-axis binning16 /other24. Belowfloor
  requests clamp to validminimum (documented integer-control behavior) rather
  than programming invalid timing. No exact siliconminimum/globalmaxFPS claim;
  tiny/large min-rate source/delivered differences still require diagnosis.
- **Both starting inputs, unmodified --streaming60 compliance83/83 each**, two
  warnings each. Prior front-start hang gone. BOTH sensor and video sampled
  states saved before entire tool and restored per case, stronger than the old
  selected-sensor-only wrappers. Scope MMAP/basic stream, NOT allformats/full
  intervals/DMABUF(expbuf device not supplied) or image/3A quality.
- Original3876frames,96 warmgeometry and14+21 explicit30fps matrices1680frames
  pass; five idle crop extremes still pass. Final960frame30/15fps recovery
  before the independently restored fast-mode gate passes, no newdmesg.
- Known working **front4x4 and1298x32 at120fps** preserved:240frames each,
  four phases all within1%, no exposure override. This disproves a blanket
  30/60fps cap; it does not prove every high-rate format or reported maximum.
- Cold/post10sRTC zero-PCM RT5659/DAC_REF/dualTFA electrical checks pass,
  no mixer/cache repair or audible tones. Independent secondRTC functional
  resume passes, S0I3delta9,817,760us, sameboot/debugflags restored. Acoustic
  confirmation remains deferred; this is NOT a hearing result.

### Retained failed short cadence / no invented cause

Initial six short metadata cases each return48 valid frames and pass ALL
frame/ABI checks, but front phases29.38–29.75fps fail the unchanged1% gate.
Main14-gate batch therefore has a real failed script, NOT allgreen. Original
report retained. Independent six long240-frame cases =1440 frames all pass
the SAME1%/metadata/ownership/crop/payload assertions after other tests.

Readonly clock queries (adjtimex modes0, no clock changes) later measure
MONOTONIC/RAW ratios1.00032495 and1.00009617, currentclocksourceTSC(tsc).
The latter sidecar runs concurrently with the long pass, not the earlier
failed window. Thus it does NOT prove the cause of the initial2% deviation;
no PLL/NTP/clock-calibration explanation asserted as fact, no thresholds
relaxed or failure relabeled. Early failure still needs simultaneous capture/
clock evidence if reproducible. Nonzero perframe ISP programming, error-frame
injection and realPM/I2C rollback still host-only or untested.

### Full integration scope remains open

Later evidence-only commits do not alter this tested kernel source. GUI/
photos/recording/pixelquality/full3A/AWB were NOT tested on R16. ACTIVE subdev
mutation/lock/control-error transactions, fullintervals and high-rate source/
delivery mismatch remain. Compat32/MediaRequests and broader hardware remain
open. Flash-tools' current integration stager tested against this published
R16 source:22 payloadfiles,16 nativePKGBUILD checksums,8staging/9preflight
fixtures and shell/YAML checks pass; unrelatedAF bytes preserved. No full
kernelpackage/DNX/rootfs/USBimage build or imageboot was dispatched/proven.
Do not call this full objective complete merely from the new green scopes.

Control-range primary reference:
https://www.kernel.org/doc/html/v6.19-rc2/userspace-api/media/v4l/vidioc-g-ctrl.html
