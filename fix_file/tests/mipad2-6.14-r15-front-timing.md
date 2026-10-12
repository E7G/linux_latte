# R15 front-start timeout: VBLANK isolation, not a completed timing fix

2026-10-12, same R15 kernel and boot as the prior validation. No restart,
kernel patch, default promotion, GUI opening or audible tone.

## Live stalled state

A second bounded 50-second syscall/stack trace added getter-only video and
BOTH sensor snapshots, plus read-only timing registers on powered sensors.
Five snapshots (20–41 seconds) consistently returned actual G_INPUT **0**,
OV5693 active/STREAM=1, reported and physical1296x736, HTS2688, VTS740,
VBLANK4, binning step0x31/0x31. T4KA3 was suspended, never forced awake
for register sampling. Main thread stayed in vb2_core_dqbuf; the traced
process group was terminated/reaped. Video format, selected input, reported
period AND both sensors' sampled format/crop/controls were restored exactly.

**Correction of interpretation:** stdout's last heading “Buffer ioctls
(Input1)” identifies the tool's iteration, NOT the actual selected sensor
when it stalls. Live G_INPUT is0. Do not infer a rear-camera failure from
that heading, or a pthread wait/STREAMOFF deadlock from a main-thread DQBUF.

## Controlled independent reproduction

Kept front video1280x720/sensor1296x736, used the same default-no-S_PARM
fixture with all48-frame payload/metadata/ownership/restart/takeover checks.
Changed only queue count2 versus8 and the requested blanking/period setting.
No exposure override. Each case reinitializes S_FMT then its intended timing.

| Setting | Live VTS | 2 buffers | 8 buffers | Observed cadence |
|---|---:|---|---|---|
| VBLANK4 |740|0 frames, timeout|0 frames, timeout|none|
| VBLANK16 |752|48 frames, exit0|48 frames, exit0|about79fps|
| VBLANK64 |800|48 frames, exit0|48 frames, exit0|about74.4fps|
| explicit S_PARM30 |1984|48 frames, exit0|48 frames, exit0|30fps, all four phases within1%|

Thus at this geometry, VBLANK4 independently reproduces the no-frame
condition in both small and large pools; increasing blanking restores
capturing without changing pool size. Merely increasing the buffer pool
does NOT fix this trigger. This does not identify the sensor/CSI/ISP
internal failure mechanism, prove the exact physical minimum blanking,
or validate other geometries/rates. **No arbitrary global FPS ceiling.**

The first harness copied a new executable through Windows SCP without
preserving executable mode: its two-buffer cases returned126, not driver
failures. Those original reports are retained. A distinct v2 report verifies
the binary SHA and executable mode BEFORE sensor changes and reruns all
eight cases. Never recast exit126 as a kernel regression or overwrite it.

## Android evidence / next patch requirements

Pinned Mi Pad2 Android source d2afb1de9a761ff01dafdf9efe4736e521ab71f6,
micam/ov5693.h's1296x736 mode, uses HTS2688 and VTS1984 at30fps. The
original exposure implementation starts from the mode-table VTS and only
extends it for long exposure. This supports a known working30fps baseline,
NOT a universal16-line blanking minimum for every arbitrary crop.

The current Linux OV driver advertises minimum VBLANK4 at every format;
that advertised boundary demonstrably fails here. Next work must make
advertised timing/defaults consistent with the selected mode and measured
streaming, cover tiny/unbinned/large crop boundaries, preserve working high
rates and verify truthful interval enumeration. Do not silently repair the
test tool's controls, change its pass thresholds, or claim an assisted run
is unmodified full compliance. All prior R15 negative results remain valid.

Kernel source unchanged; integration goal still active/incomplete. Structured
rows and original-evidence hashes: adjacent front-timing-isolation-summary.

Primary source:
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/ov5693.h
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/ov5693.c
- https://raw.githubusercontent.com/gjasny/v4l-utils/v4l-utils-1.32.0/utils/v4l2-compliance/v4l2-test-buffers.cpp
