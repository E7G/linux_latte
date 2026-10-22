# Mi Pad 2 6.14 r11: measured cadence fix, restart still fails

Measured 2026-10-11. Built source `544c0902e4d4b8a1135b69ed621437e0bf91fe1a`.
Release `6.14.0-mipad2-integrated-r11`, boot ID
`d81f8a6a-8f25-40a5-8145-177ac52695cb`. One-shot boot reached SSH and USB
serial. Saved GRUB default remains bqdiag1; next_entry consumed. Not complete
kernel support: the additional ordinary-restart gate failed (below).

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
- Strict r11 device C gate compiled -Wall -Wextra -Werror and passed on both sensors.

## Required real gates

For each input, discover matching sensor subdev and snapshot crop/format/
controls; restore with readback even on failure. Camera application must be
gracefully closed, SSH + USB serial + no-idle enabled before one-shot reboot.

- Original strict multiopen and extended 960-frame queue regressions.
- Correct-node standard streamparm ABI; ensure sensor period readback agrees.
- 30 and 15 fps cadence within 1% before/after observer closure and surviving
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

## Hardware follow-up

LLVM21 ThinLTO W=1 full build exit0; 34 module CMS signatures verified.
Source/HEAD and protected r10 build artifacts unchanged during build.
Kernel SHA256 `22edf667be9253f9bdbd79caee47b33f6d22468e19c651c052b1acf3f81f0ad7`.
Bundle SHA256 `e306ccb2f44b473f0d726c5ba8b7e61a295a756e31db6532ccac2a9bc2188b4f`.
Serial initrd SHA256 `17c040fc25ca51f5c5976f76087a36227bf494aff3f04b451100e5af9fe281ed`.
Existing build warnings retained. Stable kernel/module trees not replaced.

Before reboot, grub-fstest first failed a serial-initrd comparison. Later it
could not find either old or new candidate paths. sync/drop_caches=3 restored
raw reads; kernel, normal initrd and serial initrd byte comparisons passed.
This is consistent with stale raw-device page cache, not filesystem repair.
Normal-initrd pre-generation hash was not persisted; its unchanged flag is
null rather than falsely claiming an independently saved hash check.

Both sensors passed original strict 18-frame and separate 960-frame runs,
correct-node streamparm ABI, owner isolation and surviving-fd takeover:
1,956 strict payload/sequence frames. Separate cadence/exposure test returned
720 valid frames (four sensor/rate cases, three phases of60). Sensor crop,
format and all sampled controls restored with readback and no errors.

| Input/request | Before observer close | After close | Surviving-fd takeover |
|---|---:|---:|---:|
| Front30 |30.001|30.006|30.001|
| Front15 |15.000|15.000|15.001|
| Rear30 |30.012|30.017|30.014|
| Rear15 |15.006|15.006|15.006|

All cadence phases passed1% tolerance. Both REQBUFS calls retained1280x720,
pixelformat, stride, sizeimage and high exposure. Front exposure1482/2970
and rear1864/3733 were unchanged for30/15fps respectively. These are real
positive checks of the earlier r10 takeover failure, not relaxed assertions.

10-second RTC s2idle resumed with same boot ID; S0I3 +9,830,112us.
Post-resume hardware smoke passed. Silent PCM verified DAC_REF hardware
registers and both amplifiers active/idle without mixer/cache repair.
User heard both440Hz1-second tones at unchanged volume0.47. No kernel
BUG/WARNING/UBSAN/Call Trace in the electrical/resume audit.

## Retained new negative gate: ordinary restart

A separate test omitted S_FMT inside a fresh capture fd while reusing a
previously selected video format. Initial/observer-close phases kept30/15fps
on both sensors. It then performed STREAMOFF, requeued all mapped buffers,
and STREAMON WITHOUT another REQBUFS/S_FMT. All four cases timed out with
CSS enqueue -EINVAL. Outer sensor state restored exactly. No ordinary
restart PASS claimed, and pristine never-configured fallback is not proven
by this cached-format test. Source lead: CSS stop clears pipe configs and
queue_setup reconstruction is bypassed when existing MMAP buffers are reused.

## Desktop: separate Snapshot shutdown correction

The earlier r5 reopen gate checked preview but not service exit status.
r10 captured SIGSEGV in GstGL/Mesa at process exit while camera streaming
threads were still alive. The main thread was in libc exit/Mesa worker
cleanup. Exact Mesa root cause is unproven; kernel BUG is not indicated.

Snapshot r6 source `db794b2fe85c72dd77710880bbc45ca3909ace1a` explicitly
stops camera streaming in application shutdown and window close_request.
GApplication::quit otherwise only calls shutdown, not window close_request:
[Gio primary documentation](https://docs.gtk.org/gio/method.Application.quit.html).
Offline full workspace tests and release build passed (existing warnings).
On r11, user confirmed preview. Initial session +3 reopens each had native
MMAP/continuing AE and actual systemd Result=success, MainPID=0,
ExecMainStatus=0 after GDBus quit. This proves four clean quit closures in
this run, not exhaustive Mesa/recording/window-X stability. Default launcher
now points to r6; r5 binary and launcher rollback backup retained. No new
photos or full AWB/3A confirmation claimed.

CREATE_BUFS undersized/oversized negative baseline remains from r10. A
2.7-million-case ASan/UBSan prototype is outside production source, unbooted.
Scaling/ENUM_FRAMEINTERVALS/full streaming compliance/AWB remain open.
Machine-readable companion: mipad2-6.14-r11-results.json.
