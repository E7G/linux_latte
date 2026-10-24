# MiPad2 7.2 r5: encoder submission stalls and capture backpressure

## 2026-10-25 correction: actual H.264 backend measured

Later private-driver counters show the legacy Gen8 AVC post-pack loop below
was **not selected**. Gen8/CherryView H.264 delegates to the Gen9 AVC backend.
The selected VME run stage, not resource allocation, dominates measured encoder
wall time. Cadence still fails. See [actual backend, failed first coverage guard,
corrected measurements and limits](MIPAD2_R5_SELECTED_VME_7_2.md).
The historical source lead below must not be read as measured BRC re-encoding.

## CONT28, 2026-10-24: localization evidence, NOT a performance fix

Three distinct diagnostic windows keep foreground preview, 1080p H.264 around
15 Mbit/s and AAC 48 kHz stereo. Requested 20 seconds to bound diagnostic data;
observed MP4 spans were 24.56-25.14 seconds. These are not full recording or
Android-parity qualification. Cadence still fails; failed clips are preserved.

| Instrumentation | Measured fps | MP4 maximum gap | Gaps >50 ms |
|---|---:|---:|---:|
| Kernel camera events | 29.310789 | 74.000 ms | 22 |
| Kernel + bounded pad metadata | 29.358826 | 65.667 ms | 20 |
| Kernel + aggregate VA forwarding | 29.041241 | 79.000 ms | 22 |

## Driver buffers: slow return is downstream backpressure, not an isolated sensor verdict

The first trace has 730 driver completions/726 dequeues inside the marker window,
with zero trace overruns, buffer errors or V4L2 sequence discontinuities. All
dequeues join a unique queue's completion by index and common microsecond
timestamp precision (V4L2 timeval truncates native nanoseconds). Completed-to-DQ
latency median 102.414 ms, maximum 185.332 ms; 579/730 completions leave zero
buffers owned by the driver. Every >50 ms completion gap follows that empty
driver-owned state. DQ-to-requeue median 3.761 ms, max 40.011 ms. QBUF clears
timestamps, so return matching uses the next same-index QBUF, not timestamp.
This narrows the investigation; it does not prove a hardware sensor or IRQ fault.

## Actual encoder boundary and bounded frame identities

The second trace records the actual `GstVaH264Enc`/`vah264enc0` instance:
212,069 committed metadata records, 176 objects, no overflow/incomplete records.
There are 21 unmatched pre-hooks overall, but zero unmatched buffer calls in the
recording window. No blanket claim of fully paired shutdown hooks is made.
All 730 in-window encoder inputs match exactly one native-source PTS/offset pair
and have consecutive offsets. This proves that limited source-to-encoder-input
window, not all sensor SOFs, encoder output or final MP4 frame conservation.
Exact output PTS matching returned zero; output timestamp rebasing remains
unresolved rather than being silently normalized into a stronger proof.

Encoder sink chain median 32.949 ms, p95 50.335 ms, maximum 110.966 ms; encoder
src push median 0.373 ms, p95 1.129 ms. Raw asynchronous queue sink median
28.411 ms, p95 43.988 ms. Preview queue sink max 3.746 ms, preview downstream
push max 22.061 ms. The recording branch scale/convert elements mostly pass
through: measured exclusive synchronous transform medians about 6-7 us.
Inclusive call time is not CPU usage; this does not justify blindly adding
queues, changing preview thread count or forcing audio clocks on.

## VA submission, installed driver and reference source

A private forwarding diagnostic measures eleven VA API entry points, without
reading payloads, allocating or writing per frame. Three host forwarding/error/
PID-filter cases and an exclusive-output negative control passed; Werror build
had no warnings. Child plugin scanners do not write the producer's output.
Only the isolated test process uses it; default launcher/loader unchanged.

`vaEndPicture`: 738 calls, no errors, wall total **19.056 s**, thread-CPU total
**3.163 s**, maximum 65.880 ms, ten calls >50 ms. `vaSyncSurface` wall total
0.120 s, including one 61.962 ms outlier. These are whole-process aggregates,
not frame-by-frame attribution. Other APIs, notably `vaMapBuffer2`, are not
wrapped; do not claim exhaustive VA coverage. Non-CPU elapsed time can include
blocking and descheduling, not exclusively proven GPU execution.

Installed `libva-intel-driver-irql 2.4.5-1`, libva 2.24.1. Driver binary SHA256:
`1361f2012ea99c1af184aa86e159efac22cfbf5e766165377202a796e89422ad`.
The matching-version public tag resolves to
`0b648be50cd80e16469c135c76ff61bbd2f2d12b`; installed binary reproducibility has
not been established. Generic Intel 2.4.1 is not the installed fork/version.
The pinned reference has a CBR/VBR post-pack loop that maps coded output before
checking rate-control results. It is a source-supported next lead, not a measured
count of actual re-encodes or proof of a specific i915/firmware defect.

## Cleanup and next work

Only two superseded successful 6.14 source-AAC test clips were removed under the
existing obsolete-test cleanup authorization (117,892,149 bytes). All logs,
metadata, current failed media, r4 references, source-thread baselines, photos,
installed kernels and 35 private alias targets remained protected. Final audit:
2,214 protected installed files plus all 48 current payload files unchanged;
all three fresh geometry/control snapshots restored, sensors/ISP suspended,
all jobs/PCM closed, traces removed, timing library unmapped and global user
environment unchanged. Guards and requested no-lock/no-DPMS/no-auto-suspend
settings retained. No reboot, nonzero playback or production driver change.

Next: measure the actual IRQL driver's submission/BRC waits and preserve rate
control, picture quality, visible preview and real frames. Do not bypass BRC,
lower bitrate/resolution, fake timestamps or silently replace missing frames.
S5, long-run/DMA injection, optics, headset/acoustics and factory-DSP/MTP
qualification remain open. No complete kernel/system or Android-parity claim.

### Primary references

- [Pinned IRQL H.264 pipeline](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/gen8_mfc.c#L1839-L1861).
- [GStreamer queue blocking semantics](https://gstreamer.freedesktop.org/documentation/coreelements/queue.html).
- [Kernel tracefs clocks, instances and ring statistics](https://www.kernel.org/doc/html/latest/trace/ftrace.html).
- [Scalar measured evidence and limits](tests/mipad2-7.2-r5-encoder-wait-summary.json).
- [Preserved uninstrumented recording failure](MIPAD2_R5_RECORDING_REGRESSION_7_2.md).
