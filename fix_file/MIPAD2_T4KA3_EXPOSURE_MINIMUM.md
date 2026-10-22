# T4KA3 minimum integration: Xiaomi Android source comparison

2026-10-22, Linux6.14 integration candidate. No new kernel installed or booted.

Xiaomi Android's [pinned T4KA3 header](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/t4ka3.h)
defines minimum coarse integration as one line, a six-line integration margin,
and a 16-bit frame-length bound. Header SHA256:
`73f95c13b0a2771efb00f47030e91a42edb6337a33964336eb24f4832acfd032`.
Its set-exposure callback clamps requests to that minimum.

The integrated Linux driver instead advertised exposure minimum zero, both
at control creation and after VBLANK changes. With an unbinned two-line crop,
minimum VBLANK four yielded frame length six and exposure maximum zero.
This did not satisfy the OEM one-line-plus-six-margin contract.

The driver now uses one line in both exposure ranges and raises only the
necessary minimum VBLANK to retain at least one line plus margin. Normal-sized
30fps modes retain their existing frame length, defaults and gain units. This
does not change AE policy, gain quantization, color coefficients, resets or
any camera start/focus/foreground/security policy.

Validation compiles the actual range and VBLANK functions against explicitly
stubbed V4L2 control/state operations. It enumerates every even valid height
for binning1/2 with minimum/default/maximum blanking: 12,937 checks. Old source
fails 5,547 checks (two range defects, not 5,547 independent bugs); patched
source fails zero. Normal and Python-O runs agree. Adjacent geometry/TRY/busy,
metadata control and stream-parameter tests pass. These are not physical sensor
or complete V4L2 framework acceptance tests.

A separate Clang21 W=1 T4KA3 object build passes with zero warnings; r26 build
artifacts and user modifications were preserved. A complete new bzImage/modules
build, on-device exposure-boundary/stream tests, native photographs and optical
AE/AWB/AF/Android-Windows parity remain unqualified. No measured black-preview
or visible image-quality fix is claimed from this source change.

[Machine-readable scalar evidence](tests/mipad2-t4ka3-exposure-minimum-summary.json).
