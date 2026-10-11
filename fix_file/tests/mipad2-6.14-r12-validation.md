# Mi Pad 2 r12: measured restart and CREATE_BUFS fixes, remaining gaps

Prepared 2026-10-11. Driver/test source commit `67306a5e196828b8290dbfa77e09f5634d77bb3a`.
Measured 2026-10-12 on r12, built source `37f8d9498a20e83f287db2a81223cfa7c483a955`.
Stable saved boot default remains bqdiag1; r12 is a one-shot candidate.
Only the scoped hardware evidence below is claimed, not complete support.

## Changes and rationale

- CREATE_BUFS supplied plane count must be1 and size at least pix.sizeimage.
  Larger requested sizes are preserved, rather than reset to PAGE_ALIGN.
  Zero incoming planes (REQBUFS) still selects one page-aligned plane.
- Propagate statistics-buffer allocation error instead of silently succeeding.
- Ordinary stop retains CSS pipe/extra/stream format configs for restarting
  existing MMAP buffers. It still destroys pipes, stops SP, clears params.config
  and css_update_params_needed, returns stats lists, frees/zeroes css_param and
  flushes per-frame parameters. This is NOT a blind in_reset=true change;
  old reset and full-clear callers keep their original semantics.
- Existing reset/recreation remains. Before DMA, STREAMON gets CSS output info
  and compares width,height,stride,format,raw depth/order,crop to allocated frame
  layout. Getter/mismatch errors return queued buffers before MC acquisition.
  Failed CSS start additionally stops the acquired media pipeline, matching
  upstream. No owner isolation or sequence accounting gate removed.
- Existing buf_init maps vb2_plane_size via hmm_create_from_vmalloc_buf; larger
  CREATE_BUFS memory is not limited to frame.data_bytes. Real mmap/DMA tests
  still required; QUERYBUF-only success is insufficient.

## Offline evidence and limits

All production-extracted host suites passed ASan/UBSan:160,000 queue error/
restoration cases;2,700,000 CREATE_BUFS plane/size cases;420,000 CSS stop,
parameter cleanup, layout mismatch and pre-DMA error-gate cases. Existing
320,240 interval, sequence, multiopen and51 streamparm suites passed too.
Firmware, sensor controls, lists, locks and IRQs are stubbed; not hardware
DMA/lockdep/resource-failure proof. Driver diff checkpatch0 errors/warnings/
checks (131 lines). Two real-device C gates compile -Wall -Wextra -Werror;
they have NOT run. Existing host unused-parameter warnings remain.

## Required real gates — do not relax the r11 negative test

1. Original strict owner/observer/surviving-fd tests and long frame runs.
2. Both sensors30/15fps within1% before/after observer close, ordinary
   STREAMOFF/requeue/STREAMON using existing buffers, and surviving-fd takeover.
   Confirm exposure unchanged across ordinary restart and both allocations.
3. CREATE_BUFS zero/undersized/exact/oversized length and nonowner EBUSY.
4. Oversized CREATE_BUFS real MMAP + streaming on both sensors/rates; valid
   payload/sequence/cadence,1MiB beyond image payload remains0xa5, ordinary
   restart/takeover continue. Restore crop/format/controls with readback.
5. Non-streaming and appropriate streaming v4l2-compliance. Keep unresolved
   scaling/ENUM_FRAMEINTERVALS failures; do not remove tests to obtain a pass.
6. One-shot boot, USB/SSH/no-idle, RTC resume, audio electrical and acoustic,
   focused Snapshot r6/clean exit and other hardware smoke. Default unchanged.

r11 ordinary restart timed out in all4 sensor/rate cases with CSS enqueue
-EINVAL. r10 CREATE_BUFS accepted small sizes and shrank larger allocations.
Those negative reports are retained; no fixes claimed from host-only tests.
Pristine no-S_FMT fallback, recording, full AWB/3A and broad support remain.

Primary references:
- [Videobuf2 queue/size and failure-return contracts](https://www.kernel.org/doc/html/latest/driver-api/media/v4l2-videobuf2.html)
- [Upstream AtomISP start/stop and CSS-start cleanup](https://raw.githubusercontent.com/torvalds/linux/master/drivers/staging/media/atomisp/pci/atomisp_ioctl.c)

## Full-build attempt 1, compile failure — no device deployment

Pinned source 242f4530501f2f2740f0f71b82b83c51547c9789 failed in
atomisp_ioctl.c because a local variable named current expands to the x86
get_current() macro. Offline stubs had omitted this macro and therefore did
not catch the build failure. Rename to css_info and include the real current
macro definition in the source-extracted host test. Preserve failed log/state.
Resume the same isolated build directory with a separately pinned corrected
commit; no configuration change or full rebuild from scratch is required.
This is a compile fix, not a hardware-validation result.

## Hardware follow-up, 2026-10-12

Corrected full LLVM21 ThinLTO W=1 build exit0, all34 module CMS signatures
verified. The targeted real kernel-header ioctl object compiled before full
link. Seven corrected host suites passed; reintroducing the old current local
name into an in-memory fixture now fails compilation as expected. Attempt1
failure preserved, not hidden. Existing kernel build warnings remain.

Kernel SHA256 `9f0851cc364afb9291c5d1fbbd0f272c5a3feb3a8fc84e8926606a054db78d9d`.
Bundle SHA256 `31a957f8df1e21d2ea0b2c52e64adf0d3c70747fe08d8a91a8efc1c18a0aa65b`.
Serial initrd SHA256 `841004bba494b5fc2963b65b098d7852e6830def79dba445a54a7eb5a50872ee`.
One-shot boot ID `92ee1633-5c07-402e-b336-2ff8e1cf757a`; SSH and USB serial
returned. Protected stable kernel/module trees unchanged during staging;
only appended GRUB custom entry changed. saved_entry=bqdiag1, next consumed.
Normal initrd before/after serial generation hash persisted and matched;
initrd systemd verify passed, raw Btrfs byte comparisons passed.

- Both sensors: original18-frame plus separate960-frame strict multiopen,
  owner isolation, observer close, surviving-fd takeover and streamparm ABI.
- Ordinary restart: four sensor/rate cases,240 frames each, four60-frame
  phases. STREAMOFF/requeue/STREAMON uses existing MMAP buffers, no additional
  REQBUFS/S_FMT. All four cases now pass instead of r11 timeout. All measured
  phases within1% at30/15fps; exposure unchanged front1482/2970, rear1864/3733.
  This reuses an outer-selected format, not pristine unconfigured fallback.
- CREATE_BUFS size contract: zero/half/one-byte-short EINVAL; exact1384448,
  one-byte-extra1384449 and larger2433024 allocations retain requested size.
  Nonowner mutation EBUSY passes. Both sensors restored exactly.
- Oversized MMAP/DMA: four additional240-frame cases, each buffer1MiB beyond
  image payload filled0xa5 and checked after every dequeued frame. Valid
  payload/sequence, four-phase cadence, ordinary restart and takeover pass.
- Total3,876 strict/cadence/oversized capture frames. Sensor crop, format and
  sampled controls restored with readback after every gate.
- Full no-stream v4l2-compliance remains NONZERO:72/74,2 failures,2 warnings
  per run across both inputs (previous70/74). CREATE_BUFS tests now pass.
  Both Scaling tests still fail and missing interval enumeration warns.
  This is not full streaming compliance or complete ISP support.

Silent PCM cold-boot/post-resume hardware checks pass without mux/cache
repair. First10-second RTC test functionally resumed but S0I3 delta was0;
do not call that low-power entry. Subsequent15-second diagnostic suspend
entered S0I3 +15,124,480us; another10-second test with original debug flags
entered +9,850,912us. Same boot throughout, debug flags restored. Initial
zero-residency event remains unexplained, not a proven kernel regression
or a repaired cause. No BUG/WARNING/UBSAN/Call Trace in the electrical audit.

Snapshot r6 four new native-MMAP/continuing-AE sessions each actually exited
MainPID0, Resultsuccess, ExecMainStatus0 after GDBus quit. Default r6 launcher
reopened afterward and continues AE. User visual confirmation and r12 audible
confirmation pending; r11 confirmations are not reused as r12 proof.

Remaining: extreme-size negotiation/scaling, interval enumeration, full
streaming compliance, calibrated AWB/3A, recording/window-X stability and
broader hardware/end-to-end validation. Goal remains incomplete.
