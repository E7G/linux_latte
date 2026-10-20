# R23: checked PCI preparation for IUNIT power-off (research candidate)

## Defect and bounded change

The pre-power-down IRQ handshake ignored eight possible PCI configuration
operations. The MSI/bus-master disable helper ignored five. The PM-only IRQ
disable and CSI read/modify/write also ignored errors, and power-off ignored
the errno returned by pci_save_state(). Failed reads could feed invalid values
into subsequent writes; failed writes could be treated as successful setup.

Check each accessed configuration operation and translate its first error with
the actual kernel pcibios_err_to_errno(), preserving already-negative errno.
Stop the runtime power-off sequence at that error. The IRQ helper has one
unlock exit, including both existing -EAGAIN pending-interrupt cases. Its
caller's CSS shutdown still occurs BEFORE this preparation, as before.

atomisp_msi_irq_uninit() now returns int. Runtime suspend propagates it;
probe-unwind and the void remove callback log failure without replacing the
original probe errno or skipping their existing final cleanup. They remain
best-effort: failure may leave MSI/bus mastering active. Their earlier resource
release ordering is NOT fixed and is not safe-fencing evidence.

pci_save_state() failure prevents the physical power request. A failed PUNIT
power-off keeps the CPU-latency QoS constraint; only acknowledged power-off
releases it. This intentionally moves that one normal-path event after the
power call. The successful PCI/MMIO/CSS/DFS transaction order is unchanged.
The unchanged DFS helper return handling is outside this PCI-only fix.

## Exact-source host model

Compile extracted real functions and the real Linux PCI errno translator with
explicit PCI/IRQ/MMIO/CSS/DFS/QoS/PUNIT stubs, -O2 -Wall -Wextra -Werror.
544 cases: direct MSI helper; both IRQ-handshake success branches directly
and through power-off; PM-only; all nine positive/negative PCI error statuses
at each accessed configuration position; save-state/PUNIT failures; both
pending-interrupt -EAGAIN branches. Deterministic failed-read poison must not
be consumed. Locks balance, no later modeled operations occur after a
configuration failure, and failed power-off does not relax QoS.

Old source fails 537/544 modeled checks. Candidate passes 544/544, with all
successful transaction traces matching after excluding the intentional QoS
move. Portable current-source test:
python3 fix_file/tests/mipad2-pci-poweroff-host-test.py

## Limits, still open

No physical PCI fault, IUNIT reset, install, boot, or device error-recovery
test has been performed. This is NOT a full R23 kernel build or DMA safety
proof. SP/CSS termination, parameter/buffer lifetimes and failed-power release
remain open. Actual Linux pci_save_state() internally ignores some config
read errors and returns only capability-save errors; checking its return does
not make those hidden reads observable or validate all saved configuration.
PCI writes returning success do not independently prove hardware DMA idle.

Deployed tablet remains R19. Existing R19/R20 artifacts and user-dirty source
are protected. Full regression/focused-object evidence is recorded separately
only once finished. Do not promote this research candidate from stub results.

Primary API references:
- https://github.com/torvalds/linux/blob/v6.14/include/linux/pci.h
- https://github.com/torvalds/linux/blob/v6.14/drivers/pci/pci.c

## Completed offline gates, 2026-10-20

All 26 exact-source regression suites pass, including the new 544-case
power-off suite and retained PCI restore/stream-stop tests. On final source
136479068020b2479be7ab3389f94211ff65e080, Clang21 W=1 olddefconfig,
prepare/modules_prepare, atomisp_v4l2.o and atomisp_cmd.o all exit0 in a
separate focused output directory. R19/R20 artifacts and the user-modified
litmus file hash remain unchanged. This is not a full bzImage/modules build.
The first completed build/test run used functional commit462ce269; three
checkpatch alignment checks prompted a whitespace-only commit and a second
complete 26-suite/focused-object run. Final patch check:0 errors,0 warnings,
0 checks. Both runs and scratch before/after reports are retained.

See tests/mipad2-r23-host-validation-summary.json. The tablet remains on
6.14.0-mipad2-integrated-r19; no R23 install/boot/error injection occurred.
