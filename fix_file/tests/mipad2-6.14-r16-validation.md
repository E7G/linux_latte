# R16 source candidate — NOT device validated

2026-10-12. Tablet remains6.14.0-mipad2-integrated-r15, same boot and stable
savedbqdiag1. No R16 installation/boot/camera/audio/RTC claim. Full integration
objective remains active; this is a source candidate, not a finished kernel.

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
