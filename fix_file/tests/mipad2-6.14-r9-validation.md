# Mi Pad 2 6.14 r9: shared video-file ISP lifetime candidate

Source: `4f11baaf9310f12e4b2b9e8d050cf61fdcecaa80`.
Release: `6.14.0-mipad2-integrated-r9`.

Only the first file powers/initializes the shared ISP. Subsequent opens do
not reset CSS or get another PM reference. The existing vb2 owner-aware
release runs for every closing fd. Shared statistics/internal buffers,
sensor power and CSS teardown/PM put run only after the last fd closes.
This kernel has one capture video node/pipe. Existing vb2 queue ownership
helpers and format/input busy checks remain in force.

## Verified offline

- LLVM21/ThinLTO W=1 full bzImage + modules build completed, exit 0.
- r8 five protected artifacts unchanged. Config differs only LOCALVERSION.
- Source hashes and HEAD unchanged during the build; existing warnings remain.
- Real open/release and real vb2 release-helper code extracted into a host
  model passed ASan/UBSan: injected fh/no-input/PM failures, observer closure,
  owner closure with a surviving fd, 2000 ordered cycles and 16000 concurrent
  opens/closes across eight threads. PM/CSS/queue-stop operations are stubs.
- Actual r8 sensor interval/stream-parameter host regressions rerun passed.
- Device C regression compiled with -Wall -Wextra -Werror. Its wrong-kernel
  guard was checked on the host. It subsequently ran on the tablet; see the hardware follow-up below.

No real kernel lockdep/TSan, sensor power, firmware, DMA/buffer or suspend
behavior is established by these host tests. No new compliance score claimed.

## Required hardware gates

Do not reboot while the pending user-assisted Snapshot test is incomplete.
Keep stable bqdiag1 and recovery default entries unchanged. After SSH/serial/
anti-idle checks, boot only through a protected one-shot entry.

For each sensor input, snapshot controls before the device C test and restore
them afterward even on failure. The test does not switch input or restore
sensor controls itself. It saves/restores video format and checks readback.
Validate selected camera/subdev identity in the outer test runner.

1. Three simultaneous video fds, actual eight-buffer streaming.
2. Nonowner REQBUFS/QBUF/STREAMON/OFF must return EBUSY.
3. Closing an observer must leave owner streaming six good, increasing frames.
4. Unmap owner mappings before closing owner: mmap retains file references,
   so closing only the fd does not yet test release. Surviving fd must then
   allocate its own queue and stream six good, increasing frames.
5. All close followed by fresh open/capture; check PM, dmesg/errors/leaks.
6. r8 rational-period/cadence/exposure-restore gates, full compliance, dual
   camera smoke, suspend/resume and Snapshot reopen/brightness confirmation.

Latest measured compliance is still r7 64/72. Tiny-format Scaling and complete
3A remain separate open work. The experimental libcamera gain-bound fix and
Snapshot 320/8 preset are not proof of full auto exposure or white balance.

## Hardware follow-up (2026-10-11)

r9 booted as a protected one-shot candidate. Original strict multiopen test
failed because all returned buffers had sequence zero. Diagnostic-only runs
exercised observer closure and surviving-fd takeover, but were not strict
passes. CSS exposure IDs wrapped at 250 and cannot represent V4L2 drops.
Corrected cadence tests placed S_PARM after S_FMT: front 30/15 requests gave
28.63/14.31 fps, rear 30/15 gave 30.01/15.01 fps. Surviving-fd REQBUFS reset
the selected period (front ~57.33 fps, rear ~30.01 fps). Earlier wrong-node
RUN_MODE and pre-S_FMT cadence harness failures were retained, not promoted
to driver evidence. Standard ioctl handling masks private CI_MODE bits.

10-second s2idle recovery, hardware smoke and three focused native Snapshot
r5 reopens passed. User confirmed preview. r10 fixes sequence accounting;
it does not fix the cadence/takeover period issues. See r10 evidence.

## Exit-status correction (2026-10-11)

Earlier Snapshot r5 reopen checks proved preview readiness, not clean
process closure. They waited for pgrep disappearance without checking
systemd Result/ExecMainStatus. r10 later retained a GstGL/Mesa close-time
SIGSEGV. Do not interpret those earlier preview gates as crash-free exits.
See r11's separate Snapshot r6 four-closure status checks and limitations.
