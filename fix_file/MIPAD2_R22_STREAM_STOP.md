# R22 nominal stream-stop backport candidate

Based on Hans de Goede's reviewed upstream commit:
https://github.com/torvalds/linux/commit/0193cce58b196603427e925683b54f2f64ef031c

Firmware needs a queued frame to finish its stop handshake. The old6.14
driver first blocks new CSS queuing and waits up to1s for ownership to drain,
then asks the now-empty CSS pipeline to stop. Upstream removes that drain.
The old40ms stop wait also cannot cover15fps(66.7ms) or slower last frames;
upstream uses200ms. These are specific upstream findings, not a measured
claim that all device photo latency or recording stutter has been solved.

This adaptation removes the pre-stop wait/unlock window, leaves a final
frame available, moves VB2 frame return after the reset attempt, and uses
200ms for CSS last-frame completion. R20 error-return checks, fatal state,
retained format configs, reset/recreate sequencing, queue-owner MC handling,
and out-of-ISP-mutex worker cancellation remain. Unlike the upstream patch,
the stopping guard stays: it marks this port's teardown while the ISP mutex
is held, is cleared before unlock, and still protects its recovery worker.

Exact-source56-case models: oldsource38 nominal/order failures, candidate0.
The tests inspect no-drain, final queued frame, reset-before-flush order,
15fps/slower frame waits, legacy/ANN/fatal/reset/create branches. The test
hardware/clock/PM/CSS functions are explicit stubs, not physical timing or
DMA completion evidence. An initial harness build failed because no-op
logging hid a variable use under-Werror; the logging stub was corrected,
not production code or safety assertions.

## Deliberately NOT called fixed: failed-reset and stuck firmware teardown

The same models explicitly retain14 timeout-destroys-without-ack cases and
16 reset-failed buffer-return cases. Those cases are NOT safe-DMA passes.
Upstream's rationale assumes the later physical power cycle stops DMA;
R20's checked error returns expose that the power cycle itself can fail.
CSS stream/SP destruction may free resources before a verified power fence.
The void VB2 stop/release path cannot be made safe by silently retaining a
queue flag or returning an errno after resource destruction. Coordinated
resource ownership/quarantine/actual idle or physical fencing remains needed.

No R22 image has been installed or booted. Device is currently back on the
old stablebqdiag1 kernel, not the priorR19 test runtime. User is unavailable
for manually selectingR19; no remote-only reboot or new recording is done.
Host or focused-object success does not qualify this research source for
deployment. Do not mix its results with earlierR19 device evidence.

## Completed offline gates, 2026-10-15

All25 exact-source host suites exit0, including the new56-case nominal
stop/order model and retained294 PCI restore cases. W=1/Clang21 prepare,
modules_prepare, atomisp_v4l2.o, atomisp_ioctl.o and atomisp_compat_css20.o
all exit0 in a separate R22-focused output directory. Source hashes/HEAD
were unchanged during build. Five R19/R20 artifact hashes remain unchanged.
No full R22 bzImage/modules build, installation, boot or device timing test.
See tests/mipad2-r22-host-validation-summary.json for exact boundaries and
the explicitly retained14 stuck-stop and16 failed-reset model cases.
