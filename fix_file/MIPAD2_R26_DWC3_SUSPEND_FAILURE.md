# R26 candidate: retain USB controller power on failed gadget halt

Backport of upstream commit
[630a1dec3b0eba2a695b9063f1c205d585cbfec9](https://github.com/torvalds/linux/commit/630a1dec3b0eba2a695b9063f1c205d585cbfec9),
by Kuen-Han Tsai, accepted into Linux and stable, without semantic changes.
The exact downloaded upstream patch applies to this6.14 tree without fuzz.
Patch SHA256:1bd1970bd794e4e84ea8cdca2d0665605adee704f96b940a5298b1b28cfa2794.
Original report: https://lore.kernel.org/r/20250528100315.2162699-1-khtsai@google.com
Stable mirror: https://kernel.googlesource.com/pub/scm/linux/kernel/git/stable/stable-queue/+/refs/tags/v6.12.41/releases/5.15.189/usb-dwc3-abort-suspend-on-soft-disconnect-failure.patch

## Why this belongs in the integrated kernel

The actual R25 tree still ignores dwc3_gadget_suspend's return in both device
and OTG-device paths. A failed soft disconnect may restore the connection, yet
the caller continues to synchronize IRQ and tear down the powered controller.
The upstream change returns -EAGAIN after reconnecting an unhalted softconnected
gadget, and propagates that failure before core/OTG shutdown. If softconnect is
already false it completes logical disconnection and allows shutdown. Success,
host, already-runtime-suspended and automatic-OTG paths keep their behavior.
No retry loop, forced power policy, hidden error, USB-function removal or change
to camera/sound/thermal code is introduced.

R25's same-boot serial observer OFF/ON/OFF experiment measured9.52s/0/9.19s S0I3.
All outer PM callbacks reported success, but these callbacks cannot certify
that the formerly unchecked inner gadget halt succeeded. This is a concrete
upstream error-path bug found during that investigation, NOT a proven cause
or cure for zero residency. R25 is still running; no R26 hardware claim yet.
Awake configured gadget runtime_usage35 alone is not evidence of a PM leak.

## Exact-source host contract (not hardware)

The fixture compiles the two actual C functions with ordered GPIO-free USB/PM,
IRQ, locking, delay and PHY stubs. An independent event/return oracle covers
49152 combinations per variant: device/host/OTG/unknown roles, both OTG roles,
runtime suspension, auto/system PM, wake policy, softconnect, gadget presence,
four PHY bit states, both PHY quirks,0/1/2ports, and0/-ETIMEDOUT/-EBUSY/-EIO.
The old source has6912 oracle mismatches; the upstream-patched source has0,
including3456 expected error-abort cases. Normal and optimized Python runs
both compile with ASan/UBSan/leak detection and exit0. This is synthetic
control-flow/ordered-call evidence, not physical USB timing, MMIO safety under
concurrency, real lock correctness, or49152 real suspend tests.

Full regression, focused kernel compile and device deployment remain pending
at this source commit. Strict checkpatch of the exact C diff passes; checking
the untouched upstream mail also retains two metadata warnings (unavailable
Fixes commit in this checkout and the upstream stable Cc spelling), zero errors.
This is not a stable-default promotion or an OEM-parity
completion claim. Full1080p recording cadence, power-off cold-start reliability,
active-debug deep power and camera DMA/reset fencing are still open.
