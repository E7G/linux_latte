# R18 source candidate — metadata control and generic event wiring

2026-10-12. Tablet remains on recoveredR17; user confirmed front and rear
preview after disabling test patterns and resetting the rear format while
suspended. No R18 boot or real powered-format/event result is claimed.

R17 GUI hot switching produced sensor S_FMT EINVAL at1920x1440. T4 HBLANK
current160 disagreed with fixed range1504; a suspended idle reset succeeded
and restored current1504. Actual source registers read-only HBLANK with the
hardware s_ctrl callback, whose powered default case returnsEINVAL for it.
R18 registers this fixed-line-length metadata control with NULL ops, so the
generic framework can update its cached value and deliver notifications
without invoking an unsupported I2C control. Genuine exposure/I2C errors are
still propagated. This is not a full transactional format/crop rollback fix.

Both sensors now advertise HAS_EVENTS before subdev registration. Their
existing6.14 core already supplies generic control subscribe/dequeue/poll/
unsubscribe behavior. No duplicate custom event ops or fabricated events added.
The real R17 direct46-test runs failed control-event subscription on both
sensors; a real R18 rerun and additional per-fd event test remain necessary.

16 host suites passed:14 existing source-extracted regressions plus18 actual
sensor-flag/core-dispatch wiring cases and3286 actual HBLANK registration/core
call_op/T4 callback cases. PM/CCI/event helpers are stubs. Two R17-source
baselines and three intentionally regressed new fixtures compiled then failed
runtime assertions. Checkpatch and actual kernel-header driver compilation
passed. This is not hardware/full-framework/real-I2C/rollback proof.

A strictR18-only native event fixture compiles but isUNRUN. It checks both
listeners' initial/change events, poll wakeup, sequence/time, unchanged-value
silence, unsubscribe isolation and exact exposure restoration. Before actual
deployment, also prepare a bounded forced-runtime-active idle format test
with full mutable-control and PM-policy snapshots. Do not hide the powered
failure by changing to a smaller GUI format or swallowing all sensor errors.

Our R17 restoration harness omitted TEST_PATTERN:actual final OV3/T4 4 caused
AE to act on synthetic frames. Both were disabled, not reclassified as image
quality passes. Future snapshots need all mutable controls including pattern
and flips; historical reports/helpers remain unchanged. GUI readiness also
needs the actual live journal/device backend, not an assumed native log.

Required next: full pinnedR18 build/signatures/protectedstage/one-shot; real
powered-format and event tests; front/rear hot GUI switching; post-camera
S0I3 (R17 final wake succeeded but residency delta0); complete timing/control
transactions, physical high rates/all intervals, 3A/AWB/image quality/photos/
recordings, compat32/Requests, broader hardware and fullflash image build/boot.
The original full objective remains active and incomplete.

Primary references:
- https://www.kernel.org/doc/html/v6.14/driver-api/media/v4l2-subdev.html
- local6.14 drivers/media/v4l2-core/v4l2-subdev.c generic event cases
- local6.14 drivers/media/v4l2-core/v4l2-ctrls-priv.h actual call_op macro
