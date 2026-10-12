# Mi Pad 2 R14 — measured progress, NOT complete support

2026-10-12. Built source `76483e24741279e881b1970b0bbd17707e2ad35f`,
release `6.14.0-mipad2-integrated-r14`. Full isolated LLVM21/ThinLTO/W=1 build
and34 cryptographic CMS module signatures passed. R13 artifacts and pinned
source stayed unchanged. Candidate-only initrds, systemd unit verification
and raw GRUB/Btrfs byte comparisons passed; only custom.cfg was appended.
One-shot boot reached SSH and COM17. Saved default remains bqdiag1, next
selection empty. No default promotion. Package/source hashes are in the
adjacent validation summary. Later documentation/test commits do not change
the kernel code used by this build.

## Production changes and scoped PASS

- Only ISP2401 + Xiaomi Inc/Mipad2 + crop-capable OV5693: sensor input width
  at least36/aligned4 by additional padding, preserving the logical even
  output minimum4x4. Original requested width is retained near native edges;
  applicable native/binning bound and wide arithmetic protect alignment.
  Crop-capable TRY_FMT requests are bounded before padding; preview remains
  at most1920x1440. Other boards/sensors/non-crop paths are not given this
  empirical input constraint. This is not proof of a universal RAW10 rule.
- OV5693 tiny-format default VTS now covers minimum VBLANK and positive
  exposure after integration margin. Valid controls are NOT sufficient to
  prove physical streaming timing; see remaining failures below.
- Nine offline regression suites passed, including24,270 extracted real
  padding/TRY_FMT/range/VTS cases, ASan/UBSan/Werror with noted host signed
  geometry warning exclusions. Four regressed-source fixtures compile then
  fail assertions. Real W=1 driver-header compilation passed independently.
- Original3,876 hardware frames passed: owner/observer/takeover isolation,
  ordinary restart and30/15fps cadence, streamparm ABI, CREATE_BUFS size/DMA
  and full1MiB sentinel tails after each oversized-buffer frame.
- Warm retained-power front1280x960 then1280x720: live hardware output
  registers match1296x976 then1296x736;48frames each, runtime policy restored.
- Explicit30fps full14-case BOTH-sensor preview matrix now passes672frames,
  including1x1->4x4 and16384x16384->1920x1440. R13 front4x4 negative remains
  retained in its original evidence. Front21-case tiny/nonstandard-even and
  binning-boundary matrix passes1,008frames with pad_w parameter staying16.
  Requested even outputs stay exact. Four restart/takeover phases per case
  meet1% cadence and match declared payload sizes/mapping lengths.
- Live enum checks now explicitly compare ACTIVE crop-left/top/width/height,
  as well as ACTIVE VIDEO/SENSOR format and exposure/VBLANK/gain/R/B values.
  This closes the narrower crop-query coverage gap in R13's device test;
  it does not prove every future size/pixel format/image-quality scenario.
- No-stream v4l2-compliance1.32.0:74/74, two missing-interval warnings.
- Cold/post-RTC silent electrical DAC_REF/RT5659/dual-TFA checks passed
  without cache/mixer repair. Two10second RTC resumes maintained the same
  boot, with real S0I3; independent second residency delta9,129,792us.
- Two independent post-negative30/15fps restart runs passed960frames each.
  The last ran AFTER rate/VBLANK diagnostics, returned all controls/crops
  and produced no new dmesg. No fatal BUG/WARNING:CPU/UBSAN/CallTrace/Panic
  lines in collected deltas. Expected lower-case CSS timeout/flush warnings
  from intentional negatives remain retained, not relabeled as a clean run.

## Retained failures / diagnostics

1. First three matrix scripts aborted before capture because the test
   assumed CLI label `vblank`, while the control prints `vertical_blanking`.
   Original reports/logs kept. v2 queries the stable CID0x009e0901; all range,
   capture, payload, crop/control and cadence assertions remain unchanged.
   These were parser errors, NOT zero-frame hardware failures.
2. The correctly parsed default-interval matrix FAILS. Without S_PARM or
   exposure override, front4x4/8x8/16x16/22x32/640x480 each have legal default
   controls butzero frames then timeout. Default1280x960/1280x720 each deliver
   48frames at about60fps. A30fps probe alone would hide this problem.
3. Requested60/120fps20-case diagnosis captured16*48=768frames, but four
   front cases timed out and the strict1% timing gate FAILED. Rear1920x1440
   reports51.205fps but delivers roughly31–32fps. Front4x4/1298x32 at120fps
   do capture; a blanket60fps limit is not proven. No max-rate support claim.
4. Front VBLANK24-case sweep retains11zero-frame failures and13*48=624
   positive frames. Among tested4/8/12/16/32/64, streaming starts at12 for
   4x4/640x480,16 for1280x720,32 for1920x1440. These are sampled thresholds,
   not exact hardware minima. Tiny and large delivered cadence can diverge
   strongly from G_PARM even when frames arrive. More blanking alone is not
   complete timing/interval validation; raw transport/ISP/capture layers
   require live timing-register and sequence tests before arbitrary limits.
5. Real --streaming=60 compliance FAILS: starting input0 times out at180s
   after metadata/buffer tests, before a streaming summary; input1 ends
   83tests/77success/6failure/2warnings. First MMAP DQBUF fails g_request_fd(),
   then remaining variants cascade through can_stream. Both processes reaped,
   camera ownership cleared and sensor state restored. Local DQBUF wrapper
   rewrites the request_fd/reserved union with legacy exp_id, and reserved2
   with frame_config_id, after VB2 clears them. This is a concrete legacy
   ABI collision. Audit private 3A/per-frame consumers before changing tags;
   do not assume the input0 timeout has the same cause.

The aggregate9,060 captured frames includes partial high-rate diagnostics,
NOT9,060 passing timing/compliance cases. No acoustic tones were played;
user deferred listening. R14 Snapshot GUI, photos, recording, pixel/3A/AWB
quality and broader hardware/flash-tools integration remain unvalidated.
Goal remains active. See [open timing/ABI audit](mipad2-6.14-r14-open-timing-audit.md)
and [structured validation summary](mipad2-6.14-r14-validation-summary.json).

Primary API/test references checked:
- https://www.kernel.org/doc/html/latest/driver-api/media/camera-sensor.html
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-enum-frameintervals.html
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-g-parm.html
- https://raw.githubusercontent.com/gjasny/v4l-utils/v4l-utils-1.32.0/utils/v4l2-compliance/v4l2-test-buffers.cpp
