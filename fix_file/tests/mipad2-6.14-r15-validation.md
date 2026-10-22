# Mi Pad 2 R15 — real ABI/crop gains, not complete enablement

2026-10-12. Built source616abdb8f2da5ac9bf23edc05cbee194ed03c4cc,
kernel6.14.0-mipad2-integrated-r15. One-shot boot reached SSH/COM17; stable
saved defaultbqdiag1/nextempty. No default promotion, tones or GUI opening.
Hashes and detailed positive/negative rows are in the adjacent summary.
Later evidence-only commits do not alter the tested kernel sources.

## Build and source

Full isolated LLVM21 ThinLTO W=1 targets compiled. Original exec handle
disappeared after make printed bzImage ready; no build/make process remained,
but its final exit code/state write was unobserved. Do NOT call that an
observed originalexit0 or restart the whole build. Existing outputs were
reverified with incremental fullbzImage/modules targets, exit0, same pinned
source/config and protectedR14 artifact hashes. Original build log retained.
34 CMS module signatures verified, embedded config/release checked. Protected
stage/normalinitrd, serialunitverify and rawGRUB/Btrfs byte comparisons pass;
onlycustom.cfg appended and one-shot consumed once.

The Android source pin d2afb1de9a761ff01dafdf9efe4736e521ab71f6 confirms
exp_id<<16 in reserved, configID in reserved2. Linux6.14/master instead
write rawexp_id into the request_fd alias. New STANDARD0 file handles leave
VB2 fields intact and do not interpret reserved2 as privateperframe settings.
Explicit preallocation LEGACY1(raw6.14)/ANDROID2(shifted) preserve oldlayouts;
they are deliberately NONstandard modes, not standard-compliance claims.
Typed32byte FRAME_METADATA correlates snapshot IDs withDQ index/sequence/
timevaltimestamp_us, under perFH spinlock, invalidated on successfulQBUF.
It is not a live buffer pointer or later3A-stat authorization. Mode changes
use queueTRYLOCK underISPmutex and reject allocated queues. ExtendedFH starts
withv4l2_fh for genericfree. QBUF owner checks precede sharedconfig mutation;
VB2error rolls it back. FullMediaRequests/compat32 remain unfinished.

OVcrop/format clamps precedeALIGN and leave nonempty native-edge rectangles,
preventing signed/unsigned alignment overflow and zero-crop laterdivisions.
Streaming-mutation/lock/control-error transactions are NOT thereby solved.
Eleven host suites,1506metadata/5850edge cases and five deliberate negative
fixtures pass; real header compilation andcheckpatchclean. Hoststubs aren't
proof of realIRQ, per-frame3A programming or full32bit transport.

## New real gates

- STANDARD0, LEGACY1, ANDROID2 on BOTH sensors: six longcases240frames each
  =1440frames, four owner/observer/restart/takeover phases,1%30fps gates pass.
  Every frame checks typed metadata keys, zero standardreserved/requestfields
  or exactlegacy encoding, wrongtimestamp/sequence EAGAIN, requeueinvalidation,
  busy mode rejection/observerisolation, ACTIVE crop/format/control preservation
  and payload/mapping limits. Real nonzeroisp_config_id programming and injected
  error-frame paths remain HOST-ONLY, not hardware-validated3A behavior.
- Earlier six shortcases48frames each all returned288valid frames and passed
  ABI/payload checks, but initial frontend30.46/30.32fps phases FAILED1%.
  Original failure kept. Longverification used unchanged1%/allother asserts;
  its success does not prove why startup shortcadence drift happened or make
  the original run PASS. Clocksource inspection observedtsc, no causal proof.
- Five idle OV selection/format extremes, including nativeedge andINT_MIN/
  INT_MAX/UINT_MAX, now return positive bounded geometry and valid format;
  sampled crop/format/controls restored exactly. No edge stream/image tested.
- Original3876frames,96 warm kept-powered frames, BOTH14-case and frontend
  21-case explicit30fps matrices(1680frames) passed with enhanced metadata
  checks. Five default-withoutS_PARM frontend zero-frame failures REMAIN;
  two~60fps defaults supplied96frames. Source arithmetic fixes do not prove
  all physical timing/default support.
- Nostreamcompliance74/74, warnings2. Startinginput1 real --streaming60
  now83/83, warnings2: the old request_fd-triggered MMAP failures are gone.
  This is a scoped rear-start streaming success, not allformats/intervals
  orDMABUF(import/export externaldevice was not supplied) validation.
- Startinginput0 compliance STILLtimesout180s during input1 buffer stage,
  before a streaming summary. A bounded strace50s reproduced mainthread
  vb2_core_dqbuf afterREQBUFS2, twoQBUFs andSTREAMON0, not the hypothesized
  worker-thread blocking-wait test. Cause NOTproven. Tracedgroup was reaped;
  BOTHsensor states snapshotted before the wholetool and restored afterward.
  Earlier per-input compliance wrappers prove only the selected sensor's
  restoration; a killed tool may have changed the other sensor. Do not
  silently extend that narrower assertion to full pre-tool device state.
- Post-all-negative960frame30/15fps recovery passed with exactselectedsensor
  restoration/no newdmesg. Cold/post10sRTC silent DAC_REF/RT5659/dualTFA
  electrical checks passed. Independent second10sRTC S0I3delta9,023,072us,
  sameboot. No fatalBUG/WARNING:CPU/UBSAN/CallTrace/Panic in collected deltas;
  expected CSS timeout/flush warnings kept.

Aggregate8436capturedframes includes the shortcadence-FAILED run, NOT8436
fully passing cadence/compliance cases. Acoustic/UI/photos/recording/3A/AWB
quality weren't validated onR15. User hearing deferred; no tones played.

## Next work / remaining full scope

Inspect stalled input selection, both sensorACTIVE/CTRL state and live
HTS/VTS/binning/output registers; compare two-buffer and larger-pool capture,
input switching, pre/postREQBUFS configuration and source/delivered sequence
gaps. Don't guessmissingwaitcallbacks, PLL cause or arbitraryFPS limits.
Correct v4l-utils blocking-wait source was consulted, but trace places this
hang in a mainDQBUF before that later test. Full intervalenumeration,
default/high-rate timing correctness, full3A/AWB, appGUI/Mesa/recording,
otherhardware andflash-toolsintegration remain open. Goal staysactive.

Primary references:
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/buffer.html
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_ioctl.c
- https://raw.githubusercontent.com/gjasny/v4l-utils/v4l-utils-1.32.0/utils/v4l2-compliance/v4l2-test-buffers.cpp

## Follow-up: front timing isolation

Getter/live-register tracing now proves actual blocked input0/OV5693, despite
the tool's last stdout input1 heading. At1280x720, VBLANK4/VTS740 produces
zero frames with2 or8 buffers; VBLANK16/64 or explicit30fps restores48-frame
checks in both pools. No kernel timing patch yet; no physical minimum or
global FPS ceiling inferred. See [scoped evidence](mipad2-6.14-r15-front-timing.md).
