# Mi Pad 2 R14 geometry candidate — not hardware validated

Prepared 2026-10-12. Device remains R13. Stable saved default remains
bqdiag1. No R14 boot, DMA, image quality, acoustic or compliance PASS claimed.

## Scoped changes

- Only ISP2401 + Xiaomi Inc/Mipad2 + crop-capable OV5693: pad the sensor
  input to at least 36 pixels wide, aligned to four, keeping requested even
  output dimensions. This is an empirical platform constraint, not a claim
  about a universal sensor or RAW10 requirement. Use the original requested
  width rather than the locally active-array-clipped width for alignment.
  Bound by the applicable native/binning geometry and use wide arithmetic.
- Crop-capable TRY_FMT requests are bounded by valid native dimensions
  before padding/alignment. This prevents huge non-preview requests reaching
  sensor arithmetic unchanged. Non-crop behavior and preview1920x1440 bound
  remain unchanged. The ordinary valid even output minimum stays4x4.
- OV5693 default VTS must cover minimum VBLANK and a positive exposure after
  the integration margin, even on tiny crops. Normal default VTS is retained
  when already valid. Valid native-format heights remain the input contract.
  This is a separate control-arithmetic defect, not the proven cause of R13's
  width-dependent capture timeout; ignored control errors remain a wider audit.

## Retained hardware baseline

R13 front4x4/8x8/16x16 captured zero frames and timed out with defaultpad16;
rear4x4 worked. Temporarypad changes retained logical4x4 output: input36/40/
44/52 streamed48frames, input20/28/32/34/38 failed. Ten additional logical
even widths18..1302 with temporary min36/aligned4 input captured48frames each.
Every diagnostic restoredpad16, runtime policies and sampled sensor state.
These results motivate the source change but do not validate R14 or identify
the causal RAW/sensor-window/ISP layer. R13 fullmatrixFAIL remains retained.

## Offline regression

24,270 extracted real padding/TRY_FMT/range/VTS function cases under
ASan/UBSan/Werror. Sensor, DMI and format calls remain stubs. Some host signed
geometry warning classes are excluded to accommodate kernel min macros;
actual W=1 kernel-header compilation is required independently. Four in-memory
regressions (no padding, clipped request alignment, no native bound, old VTS)
compile then fail assertions. The previous eight suites pass. Driver diff
checkpatch has0errors/warnings/checks. This is not a hardware or image gate.

## Required device gates

Original queue/cadence/streamparm/CREATE_BUFS/tail checks; both sensors full
14-case preview matrix including4x4 and huge requests; nonstandard even widths
with default pad parameter unchanged; warm retained-power mode registers;
default VBLANK valid and observed, no fatal kernel traces; live enumeration
preserves ACTIVE format, crop-left/top and sampled controls; RTC/S0I3; silent
audio electrical checks. User hearing deferred, no unsolicited tones.

Frame-interval enumeration, full streaming compliance, image/3A/AWB quality,
Snapshot GUI/recording/close tests and broader hardware/flash-tools remain open.

Primary references:
- https://www.kernel.org/doc/html/latest/driver-api/media/camera-sensor.html
- https://github.com/torvalds/linux/blob/master/drivers/media/i2c/ov5693.c
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-enum-framesizes.html
