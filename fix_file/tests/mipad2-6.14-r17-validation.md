# R17 scoped hardware evidence — integration still incomplete

2026-10-12. Built source `9b3361d4ba6bf4e471e9df709366d4e286c3db1a`,
one-shot kernel `6.14.0-mipad2-integrated-r17`, boot
`727d5d87-69d5-472d-8a33-86a9fb4fcd72`. Stable saved default stays
`mipad2-bqdiag1`; R16 protected build artifacts unchanged. No production
default replacement. Full objective remains active.

## Actual source defects / fixes

- OV5693 set_fmt wrote private ACTIVE format before taking its mutex;
  set_selection had no private-state lock or streaming guard. get_fmt ignored
  which and returned ACTIVE for TRY. The frame-size reader also accessed
  private ACTIVE crop unlocked. Now ACTIVE geometry readers/writers serialize
  on the sensor's private lock, ACTIVE format/crop changes during streaming
  returnEBUSY BEFORE mutation, and getters honor validpad/which/TRY state.
- Each OV TRY state receives a locked crop/format snapshot through init_state;
  the legacy private ACTIVE representation is deliberately not half-migrated
  to managed state. Valid TRY requests still work while streaming and stay
  per-state, not global. No double-lock with a shared managed ACTIVE lock added.
- T4KA3 already uses managed state with sd.state_lock equal to its control
  handler lock. Its pad callback runs under that core-held lock; it must NOT
  mutex_lock again. Explicit lockdep assertion checks this contract. ACTIVE
  crop changes now reject streaming; ACTIVE set_fmt checks busy BEFORE changing
  the caller's format argument. Valid TRY remains usable while streaming.
- T4 positions/sizes and direct-format sizes now clamp BEFOREALIGN and leave
  at least2pixels at the native edge, mirroring the OV arithmetic fix. No
  zero/overflowing rectangles fromINT_MIN/INT_MAX/UINT_MAX requests.
- T4 crop window calculation now uses the NEW rectangle and also recalculates
  position-only changes. Previously it used the oldcrop and skipped position
  updates entirely. This is software-window coherence, NOT a new calibrated
  sensor timing or pixel-quality result.

## Verified offline scope

Fourteen source-extracted suites PASS. New suite:3624 actual geometry/TRY/
busy/edge/window cases and150000 concurrent callback operations with real
pthread mutexes/control/state stubs underASan/UBSan/Werror. Instrumented
ACTIVE accessor returns assert lock ownership before the first access;
real-code control callbacks also assert the lock. Managed T4's error-check
pthread lock catches a double-lock instead of silently hanging.

Seven deliberately regressed source fixtures compile then fail assertions:
OVbusy, T4cropbusy, wrongTRYgetter, oldT4bounds, oldT4window ordering,
missingOVlock, and T4doublelock. Existing metadata/owner/queue/interval/CSS/
crop/multiopen suites still pass. Host models do NOT prove reallockdep,
I2C/PM faults, DMA/IRQ or all frame-state transactions. ActualW=1 kernel
driver/header objects compile after final stylecleanup; checkpatchclean.

## Actual runtime results and retained failures

Full LLVM21 ThinLTO bzImage/modules build passed (W=1). All34 detached module
CMS signatures verified with the build certificate. Protected append-only
stage and early serial initrd verified; actual R17 boot/SSH/USB serial recovered.
The original C: disk precheck was incorrect: WSL ext4.vhdx is on D:, with194GiB
host free. Corrected checks cover D: host, Linux build and C: delivery separately;
no files deleted to get a build through.

15 serial hardware scripts completed:14 exits0, one retained failure. The
strict R17-only fixture actually ran on BOTH sensors, metadata layouts0/1/2:
6cases x240frames =1440frames. ACTIVE identical/changed format and crop
returnedEBUSY unchanged in24 capture phases. TRY changes were effective but
anotherFD's TRY format/crop and ACTIVE stayed unchanged. These same phases
passed owner/restart/takeover/metadata/payload checks and measured30fps within1%.
Ten idle signed/unsigned crop/format extremes across both sensors passed with
sampled restoration. Never send these guarded ACTIVE probes to R16.

The39 default/min cases all delivered240frames:26 default no-S_PARM/no-exposure
override cases =6240frames, thirteen front advertised-min cases =3120frames.
Default cadence stayed within1%; minimum cases prove nonfreezing/ABI, not a
physical maximum FPS. Both-start unmodified video streaming compliance passed
83/83 each (warnings2). Strict queues, ordinary restart, CREATE_BUFS contracts,
warm modes, explicit30fps scaling/even-size matrices and long metadata gates
also passed. This does NOT establish complete imagery or all frame intervals.

Direct sensor compliance **failed45/46 on each sensor**: control event
subscription for User Controls. Both drivers omit HAS_EVENTS; their current
core supplies the generic control subscription/dequeue/unsubscribe path only
when that flag is set. The tool output contained no pad-geometry section;
do not equate this46-test generic ioctl result with complete pad compliance.
The independent strict geometry fixture above did exercise actual pad ioctls.

Silent RT5659/DAC_REF/dualTFA cold/post-RTC electrical gates passed. Acoustic
validation is deferred at the user's request. Initial10s RTC added9,759,520us
S0I3. **Final post-camera10s RTC woke successfully but added0us S0I3**;
functional wake is not low-power residency success. Debug flags restored.

GUI is NOT passed: first automated readiness window missed startup and had no
native-MMAP log. Later user confirmed front normal, rear black. Rear switching
logged sensor S_FMT EINVAL at1920x1440. T4 read-only HBLANK currently has a
hardware s_ctrl callback that rejects unknown controls while powered. During
failure its current value160 disagreed with fixed range1504. Closing cleanly,
letting the sensor suspend and setting the same format succeeded and repaired
that metadata. A powered reproduction and source correction remain required;
the newly reopened GUI was user-confirmed rear normal after the idle format reset.
This recovery is not a source fix or a powered hot-format regression pass.
The same case has not been compared on R16; do not call it R17-introduced.
No photos/recording pass.

**Own restoration harness defect:** sampled controls omitted TEST_PATTERN.
After compliance the actual values were OV3/T4 4. The GUI AE therefore drove
front exposure to minimum using synthetic bars. Both patterns were disabled
after detection; front real-scene AE subsequently converged and the user
confirmed front normal. Future snapshots must include pattern/flips and all
mutable controls. Earlier frame/timing/queue proofs are not pixel/AE/AWB proofs.
Historical raw reports and failures are retained, not overwritten as green.

See [machine-readable scoped summary](mipad2-6.14-r17-validation-summary.json).

## Explicit incomplete dependencies / next verification

This geometry pass does NOT yet make control-range updates atomic or restore
all sensor/control/hardware state after an I2C error. OV still ignores some
control update errors; T4 propagates some but can leave partial state. Crop-only
size changes need a full dependency audit of timing/control ranges and mode
configuration before claiming a transactional crop API. Stream-stop/PM error
state reliability and real fault injection remain open. These are follow-up
requirements, not excluded from the original objective.

Next: repair powered rear format reset/control-event delivery and incomplete
control restoration, verify real GUI switching and low-power residency after
camera use. R16 early cadence deviation and physical high-rate disagreement,
full interval enumeration, geometry/control/I2C/PM error transactions,
full3A/AWB/pixelquality, photos/recording, compat32/Media Requests, broader
hardware and fullflash-image build/boot all remain within the original scope.

Primary locking/layout references:
- https://www.kernel.org/doc/html/latest/driver-api/media/v4l2-subdev.html
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/buffer.html

Primary event reference: https://www.kernel.org/doc/html/v6.14/driver-api/media/v4l2-subdev.html
