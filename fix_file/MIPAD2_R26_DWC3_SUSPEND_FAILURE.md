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


## Completed regression and focused compile

All30 canonical host suites exit0 (the previous28, severity classification,
and exact DWC3 error contract). The complete current-source49152-case contract
also passes inside that suite run. Clang21 W=1 prepare/modules_prepare and
both dwc3/core.o and dwc3/gadget.o compile successfully in a fresh isolated
R26-focused directory. Configuration differs only by LOCALVERSION. R19/R20/
R24/R25 five artifacts each, protected source, and original dirty litmus remain
unchanged. The initial untouched upstream mail checkpatch's two metadata
warnings are retained; exact C-diff checkpatch exits0.

See tests/mipad2-r26-dwc3-validation-summary.json for exact source/function/object
hashes and bounded synthetic scope. Full bzImage/modules, installation, physical
USB error behavior and S0I3 comparison are STILL PENDING. The tablet remains
on R25 with no new reboot or default/feature/power-policy change.
