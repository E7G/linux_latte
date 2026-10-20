# R24: retain host parameter owners through firmware recovery

## Concrete borrowed-pointer bug

atomisp_css_stop_internal(...,in_reset=true) intentionally retains pending
params.config pointers and css_update_params_needed. It nevertheless flushed
all pending per-frame parameter objects, freed the global CSS parameter
tables, and zeroed their owning structure. In particular a pending config
shading_table pointer outlived the global table and its four color arrays.
After recovery, applying the now-zero global update flags cannot replace
that pointer; the later config update can dereference freed heap storage.
Queued, not-yet-applied per-frame requests were also discarded before
atomisp_recover_params_queue() moved the in-flight ones back to that queue.

Retain global parameter owners and pending per-frame objects only during
in_reset. Ordinary final STREAMOFF, including the owner's STREAMOFF after a
failed recovery, still flushes/frees/zeros them. Non-reset stop and the
format-preserving stop keep their prior cleanup/config behavior. No tables
are silently replaced with defaults, no extra copy or new allocation is
added, and pending update flags/inline settings/borrowed pointers survive.

This does NOT restore every historical ISP control after reset: reapplication
of all non-pending controls needs further auditing. It also does not change
the recovery worker's current returned-frame/per-frame matching semantics.

## Before/after exact-source sanitizer evidence

Extract actual stop wrappers/internal helper, atomisp_free_css_parameters,
ia_css_shading_table_free, pending-queue flush, in-flight-to-pending recovery
and config-update helper. Compile with address/undefined/leak sanitizers and
synthetic heap/list/CSS/IRQ/consumer stubs. The sink consumes retained config
references as a subsequent config update would; no real firmware is run.

Old source: actual stop/free followed by config-update reports ASan heap-use-
after-free. 1152/1440 ownership checks fail. Candidate: no sanitizer finding,
1440/1440 checks pass. Each source run balances37440 modeled allocations/
frees on eventual final owner cleanup. Cases vary queued/in-flight requests,
pending flags, final normal/format-preserving stop, and0/1/2/8/64 resets;
the real recover helper combines retained pending and in-flight objects,
and a second final stop performs no double-free. The final-owner cleanup is
a modeled path, not a test of actual VB2 close or failed hardware reset.

The prior CSS-restart regression's reset-mode expectation was corrected:
it used stack addresses and counter-only free stubs, so it previously
expected the unsafe unconditional free. Normal-stop checks are retained;
the new heap/sanitizer test independently verifies the stronger lifetime
contract. An initial new harness compile failed on an anonymous mock stream
type and an unused counter, before any canonical edit; fixture fixed.

Portable regression: python3 fix_file/tests/mipad2-reset-params-host-test.py

## Explicit boundaries

No physical fault injection, firmware assert, new kernel deployment, image
quality/AE/WB/focus or full DMA safety claim. SP/ISP stop timeouts, CSS internal
parameter/HMM lifetime, failed-power buffers/VB2 release still need a verified
hardware fence and coordinated lifetime handling. Retaining these host owners
does NOT make the earlier CSS stream destruction or later VB2 release safe.
R19 remains deployed; no source-only PASS may promote this research kernel.

Android and current upstream contain the same unconditional parameter-free
pattern, so copying either would retain this bug, not independently fix it:
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_compat_css20.c
- https://github.com/torvalds/linux/blob/master/drivers/staging/media/atomisp/pci/atomisp_compat_css20.c

## Completed offline integration gates,2026-10-20

All27 exact-source host suites pass on code4bd0fc1ddedbd6eca449daedbad0c8f22868a4bd,
including the updated prior CSS-restart contract and new heap-lifetime suite.
Clang21 W=1 olddefconfig/prepare/modules_prepare/atomisp_compat_css20.o and
atomisp_cmd.o pass in a separate focused directory. R19/R20 artifacts and
user-dirty litmus hash preserved; final driver patch checkpatch0/0/0.
No full R24 bzImage/modules build has completed at this documentation point.
Any later full-build evidence must name its own source/outputs separately.
The focused wrapper's final human-readable line retained an R23 label; its
structured commands/hash report correctly identifies R24. No duplicate build.
See tests/mipad2-r24-host-validation-summary.json for exact boundaries.
