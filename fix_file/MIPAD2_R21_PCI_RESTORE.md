# R21 PCI restore research candidate (not a deployment gate)

## Exact error reproduced

`atomisp_restore_iunit_reg()` ignored all 16 PCI configuration write results,
performed a CSI MMIO store and returned success after a failed write.
`atomisp_power_on()` also ignored the helper's return and initialized CSS.
This is distinct from the IOSF mailbox error-return loss fixed in R20.

The candidate checks every restore write, returns the first error translated
by the kernel's actual `pcibios_err_to_errno()` helper, and does not execute
later writes/the CSI MMIO store after failure. Power-on propagates that error
without running DFS or CSS initialization. Success order is unchanged.

Exact-source functions plus the real errno translator were compiled with
explicit PCI/PUNIT/QoS/DFS/CSS/MMIO stubs: 294 cases, 288 expected failures
before the change and 294 passing afterward. Six standard positive PCIBIOS
errors, an unknown positive status, -EIO and -ENOMEM at all 16 write positions
are covered both directly and through power-on. PM-only, no saved command,
PUNIT failure and CSS initialization failure remain covered. Normal-path
transaction traces match the original. No physical fault was injected.

Portable test: `python3 fix_file/tests/mipad2-pci-restore-host-test.py`.
Full regression and focused W=1 build evidence are recorded separately once
finished; this document does not claim a full R21 bzImage/modules build.

## R20 full build now terminal

Source `9e0f82cd7b70a32c370dbfbb23b44cf9f6d5dd48` completed all three phases:
olddefconfig, eight focused objects, full LLVM/Clang21 ThinLTO bzImage/modules.
All phase exit codes are 0. The wrapper verified unchanged source/HEAD and
all five protected R19 artifacts throughout. Existing W=1/kernel-doc/stack
warnings remain; not a warning-free build. No R20 image has been staged,
installed or booted. Device remains on R19 with stable bqdiag1 boot default.

## Explicit unfinished shutdown contract

SP/ISP timeout safety remains unresolved. Exact ia_css_stop_sp host probing
has 16 cases: all six initially-running/non-idle combinations incorrectly
return 0, clear software-running and free HMM/parameter bookkeeping.
`__destroy_stream()` also continues into destruction after a 40ms stop
timeout. CSS stop ignores destroy/stop errors; normal VB2 stop still returns
frames before a checked physical power cycle. Merely returning an errno
after resources are freed is not a fix. Buffers/resources require retained
ownership until actual idle or a verified hardware power fence. Partial-
power MMIO, CSS parameter lifetimes and release need coordinated auditing.

Android reference at d2afb1de9a761ff01dafdf9efe4736e521ab71f6 uses PUNIT
status acknowledgement before declaring IUNIT power-off; its CSS stream
destroy also warns and continues after the same 40ms timeout. Copying that
code is not independent evidence that timeout resource release is safe.
Windows AIQB firmware/config binaries are not available 3A driver source.

References:
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_v4l2.c
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_compat_css20.c

R21 is an incremental research candidate. Passing stubs or compilation does
not establish physical DMA quiescence, boot recovery, or Android/Windows
camera parity. Do not promote R20/R21 on these results alone.

## Completed bounded validation

All24 retained/new exact-source host suites exit0, including the portable
294-case PCI restore fixture. A separate R21-focused output directory
completed olddefconfig, W=1 prepare/modules_prepare and atomisp_v4l2.o with
Clang21. All phase exit codes0; source hashes/commit unchanged while built.
R20 and R19 five-artifact manifests remain unchanged. No full R21 kernel or
module set was built. See tests/mipad2-r21-host-validation-summary.json.

Device-side extended testing still used R19, not this candidate: R15c app
made four30s native1080p30 recordings, maximum packet gap34.334ms and all
video/audio decodes passed. Rear decoded-frame repeats remain an explicit
open finding, not reclassified as smooth Android-equivalent motion.
https://github.com/E7G/snapshot/blob/55e4a4ba08b6b9008f62f99b2780885b370d4200/MIPAD2_RECORDING_R15C_SOAK.md
