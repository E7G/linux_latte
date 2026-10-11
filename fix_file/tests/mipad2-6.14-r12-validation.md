# Mi Pad 2 r12 queue/restart candidate — NOT hardware validated

Prepared 2026-10-11. Driver/test source commit `67306a5e196828b8290dbfa77e09f5634d77bb3a`.
Tablet remains r11, stable saved boot default bqdiag1. Build source commit
will be pinned independently in its state/manifest; no r12 hardware PASS.

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
