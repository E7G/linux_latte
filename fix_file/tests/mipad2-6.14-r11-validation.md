# Mi Pad 2 6.14 r11: cadence candidate (NOT device-validated)

Prepared 2026-10-11, built on the measured r10 baseline. Tablet remains r10
until the separate protected one-shot deployment gates pass. Stable saved
GRUB default remains bqdiag1. No r11 build/hardware PASS claimed here.

## Changes

1. OV5693 Mi Pad 2 ACPI-only timing pixel rate 160 MHz, as in pinned Android
   sensor modes. Keep historical 167.68 MHz rate on other boards. Default
   VTS, G/S_FRAME_INTERVAL and PIXEL_RATE control use the same selected rate.
   No PLL, MIPI link frequency, sensor register table or rear rate change.
2. AtomISP queue fallback after CSS teardown keeps selected video format.
   Supported frame period is saved/restored around internal S_FMT. Exposure
   is also restored after VBLANK, because temporary default VTS clamps it.
   Getter/format/period/exposure errors propagate; failed S_FMT still attempts
   timing restoration, without masking the first failure. No queue-owner
   isolation, frame completion or stream lifecycle gate is removed.

## Verified offline

- Extracted real interval pad operations: 320,240 cases, both front timing
  rates and rear rate, rational/u32 limits, reset requests and error paths.
- Extracted real queue-reconfiguration/setup operations: 150,000 cases,
  cached/default formats, supported/missing operations, no exposure control,
  first/retry CSS failures, period/exposure restoration errors. ASan/UBSan.
- Existing stream-parameter, frame-sequence and shared-lifetime host tests
  rerun passed. These still use sensor/CSS/control/lock stubs.
- Kernel driver diff checkpatch: zero errors/warnings/checks. Existing kernel
  build warnings and unrelated dirty litmus-test file remain separate.
- Strict r11 device C gate compiled -Wall -Wextra -Werror, NOT yet run.

## Required real gates

For each input, discover matching sensor subdev and snapshot crop/format/
controls; restore with readback even on failure. Camera application must be
gracefully closed, SSH + USB serial + no-idle enabled before one-shot reboot.

- Original strict multiopen and extended 960-frame queue regressions.
- Correct-node standard streamparm ABI; ensure sensor period readback agrees.
- 30 and 15 fps cadence within 5% before/after observer closure and surviving
  fd takeover. Do not count S_PARM-before-S_FMT ordering as valid measurement.
- New strict high-exposure gate: choose 75% of sensor's current exposure
  range after period selection; compare exposure and output format before/
  after both REQBUFS calls. Actual payload/sequence/timestamps must be valid.
- Fresh open/no prior S_FMT fallback, ordinary STREAMOFF/ON restart and
  post-s2idle camera/audio smoke. Confirm focused native Snapshot reopens.
- Retain full-compliance failures rather than changing test expectations.

## Negative baseline (r10, real hardware)

With 15 fps selected after S_FMT, first REQBUFS retained period and exposure.
After owner close, surviving-fd REQBUFS caused CSS get-info failure followed
by internal default S_FMT. Front exposure 3113 -> 1030 and period -> ~60 fps
reported (~57.34 measured); rear exposure 3733 -> 2486 and period -> 30 fps.
The new strict gate failed both inputs as expected. Scoped debug flags and
sensor geometry/controls restored; failure outputs retained in the adjacent
mipad2-6.14-r10-reset-baseline.json, not counted as r11 validation.

Primary timing reference:
[Pinned Android OV5693 header](https://raw.githubusercontent.com/latte-dev/android_kernel_xiaomi_latte/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/ov5693.h).

Scaling, CREATE_BUFS validation, missing ENUM_FRAMEINTERVALS support, full
AWB/3A and high-contrast application AE behavior remain open. See measured
r10 validation; these two fixes do not establish complete kernel support.
