# R17 source candidate — geometry serialization, NOT hardware validated

2026-10-12. Tablet still runsR16, bootbb66609d-07c0-466c-bce1-9067b13617c9,
stable savedbqdiag1. No R17 boot/DMA/IRQ/image/audio result claimed. Full
integration objective stays active; this does NOT close control transactions,
timing/highrate, full3A/AWB, GUI/recording or broad hardware/image-build work.

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

A strict **R17-only release-guarded** native device fixture compiles but is
UNRUN: ACTIVE identical/changedfmt+crop mustEBUSY unchanged during capture;
own TRY must actually change, anotherFD's TRY crop/format and ACTIVE must stay
unchanged; original240-frame metadata/owner/restart/takeover/crop/payload checks
remain. Never send those ACTIVE mutation probes to the unguarded R16 kernel.

## Explicit incomplete dependencies / next verification

This geometry pass does NOT yet make control-range updates atomic or restore
all sensor/control/hardware state after an I2C error. OV still ignores some
control update errors; T4 propagates some but can leave partial state. Crop-only
size changes need a full dependency audit of timing/control ranges and mode
configuration before claiming a transactional crop API. Stream-stop/PM error
state reliability and real fault injection remain open. These are follow-up
requirements, not excluded from the original objective.

Next: full pinnedR17 build/signatures/protectedstage/one-shot boot; real guarded
ACTIVE/TRY isolation while both sensors deliver frames, T4 native-edge probes
ONLY after the fix is booted, normal/default/minimum/fast/suspend/compliance
regressions. Do not claim completeness from the new host tests or a subset of
working modes. R16 early cadence deviation and source/delivered high-rate
disagreement/fullinterval enumeration, GUI/pixelquality/3A/AWB, compat32/
MediaRequests, otherhardware and fullflash-image build/boot remain retained.

Primary locking/layout references:
- https://www.kernel.org/doc/html/latest/driver-api/media/v4l2-subdev.html
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/buffer.html
