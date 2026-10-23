# 7.2 V4L2 NULL callback regression: r2 quarantined, r3 candidate

## Physical evidence (2026-10-23)

A single guarded warm reboot successfully ran exact 7.2 r2, with embedded
configuration, image, five loaded critical-module srcversions and payload hashes
verified. Fifty-one read-only first-probe checks passed, including both native
sensor probes and VCM. Runtime serial output worked. This does not establish S5
cold-start reliability or complete early-boot serial capture.

The first actual rear-camera default-format capture returned zero bytes and
`VIDIOC_QBUF returned -1 (Device or resource busy)`, despite v4l2-ctl exit zero.
No S_FMT/S_PARM or sensor-control writes were made. Front capture was not attempted.
No DDR/IUNIT/CSS/SP/ISP/BUG/WARNING faults were observed; both sensors and ISP
returned to runtime suspend. The experiment stopped, followed by one deliberate
rollback reboot to stable 6.14. Protected boot/userspace files and all 35 private
trace aliases were verified unchanged. R2's menu entry was removed by restoring
the exact previous custom.cfg; r2 images, modules and private evidence remain.
Do not boot r2 or reinterpret its earlier host gates as camera qualification.

## Root cause and fix

Actual 7.2 V4L2 reqbuf/qbuf/dqbuf dispatch and private default callbacks pass NULL
as callback private data. VB2 owns queues by file->private_data, not that NULL.
The old AtomISP owner comparison therefore returned false EBUSY; DQBUF and two
metadata helpers would dereference NULL if reached. No crashing metadata IOCTL
was deliberately sent to the physical tablet.

R3 derives all four handle contexts from file->private_data and uses the actual
public vb2_queue_is_busy(queue, file) ownership predicate. Private metadata
helpers now accept file directly. Ownership isolation, whitelist/priority checks,
32-byte typed metadata ABI, legacy wire modes and rollback semantics remain.
There is no V4L2-core patch, queue-owner bypass or userspace workaround.

## Regression oracles

The old metadata model incorrectly passed non-NULL callback data, missing the
real API boundary. It now models current ownership and NULL callbacks, retaining
1,506 metadata/error/legacy cases and rejecting four independent mutations.

The new mipad2-null-fh-dispatch-host-test.py compiles actual V4L2 req/q/dq
dispatchers, actual VB2 ioctl ownership helpers, AtomISP wrappers and the complete
AtomISP private dispatcher under ASan/UBSan. The core private NULL callsite is
inspected, not fully executed. Disabled legacy command bodies, allocation,
MMIO/DMA/interrupts/locking are explicit synthetic stubs, not hardware proof.
Against pinned r2 source the model COMPILES, then fails QBUF ownership and detects
three sanitizer faults. The identical current-source model passes all four paths.

R3 is a candidate until a new linked build, signed artifact gates and actual
dual-camera capture pass. OEM parity, acoustic/optical quality, recording cadence,
suspend/S0I3 and failed-reset DMA quiescence are not established by these tests.

## Completed r3 artifact and physical gates

Build source is `20f0304fc024a784dd2e356bd72331c9640d382e`; release is
`7.2.0-mipad2-integrated-r3`. Full bzImage/31-module link, exact embedded config,
configuration audit, all 31 real CMS signatures and native ALPM/preflight pass.
R2 artifacts remain byte-identical. Three existing ThinLTO frame-size warnings
remain; exact warnings and artifact hashes are in the JSON summary.

One serial-guarded warm reboot ran that exact image/config and verified five
loaded critical-module srcversions. All 51 first-probe checks passed. Without
S_FMT/S_PARM or sensor-control writes, rear and front each delivered four actual
default-mode frames (not just a successful tool exit), fixing r2's zero-byte
QBUF failure. This is transport proof, not optical/scene quality confirmation:
the rear sample was nearly uniform and the physical scene was not controlled.

Fourteen actual idle metadata IOCTL checks passed. The tracked
`mipad2-r15-default-format-probe.c`, changed ONLY in release guard and usage
string, then passed six cases: two sensors times standard/legacy/Android mode.
Each produced 48 frames over observer-close, normal restart and owner takeover,
for **288 frames** with typed metadata correlation/stale rejection, nonowner
REQBUFS/QBUF/STREAMON/STREAMOFF EBUSY and format/control preservation. S_FMT is
used only to restore the saved format during cleanup; S_PARM/sensor-control
writes and manual reprobes are zero. The tablet has no cc, so the identical
adapted source was built as a hash-pinned static x86-64 ELF on the host.
Source/binary/compile receipts identify this preparation issue, not a kernel
failure. No raw frame/timestamp/serial/kernel trace was exported from the tablet.

Afterwards both sensors and ISP are suspended with usage zero, no new kernel
faults, 686 protected boot/userspace files and all 35 private aliases/bytes are
unchanged, and noidle/thermal guard remain active. R3 currently runs but the
saved default stays stable 6.14; no next_entry remains. R2 stays quarantined.
Serial capture is closed and stored privately on-device. A live kernel marker
was received, but no r3 banner was captured: do not claim full early boot capture.

Open gates: controlled scene/optics, actual application preview and recording
cadence, matching audio profile/electrical/acoustic tests, S5 cold boot,
suspend/S0I3/orientation/charging regression and failed-reset DMA quiescence.
No OEM/Android parity or complete-image/Actions qualification is claimed.
