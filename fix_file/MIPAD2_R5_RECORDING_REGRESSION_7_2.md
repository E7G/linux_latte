# MiPad2 7.2 r5: normal encoded recording still fails cadence

## Later CONT27 checkpoint, 2026-10-24

Do not promote r5 as fully video-qualified. The earlier electrical/two-RTC/native
960-frame qualification remains valid within its stated limits; it did not test
normal encoded Snapshot recording. These later tests completed recording and
decoding, but failed the unchanged cadence gate. Failed clips are retained.

Same installed source Snapshot and fixed VA plugin, private settings profiles,
normal foreground window and keyboard start/stop. No diagnostic/background
capture actions, private V4L2 tracer, resolution/bitrate reduction or reboot.
H.264 1920x1080/no B-frames, approximately 14.9 Mbit/s; AAC 48 kHz stereo,
approximately 192 kbit/s. Each requested 30 seconds; actual MP4 spans follow.

| Camera | Decoded frames | Video PTS span | Measured fps | Maximum gap | Gaps >50 ms |
|---|---:|---:|---:|---:|---:|
| front | 964 | 32.809000 s | 29.351702 | 85.667 ms | 26 |
| rear | 974 | 32.688000 s | 29.766275 | 71.667 ms | 12 |

Both clips decoded fully, with no adjacent exact decoded-image repeats or
nonpositive PTS intervals. These facts do not prove source-frame conservation.
The real per-process DRM video-engine counters advanced, and expected VA/i965
libraries were mapped; exact encoder factory identity is not independently
proved. The gate still requires >29.5 fps and every positive gap <=50 ms;
neither result passes. No relaxing thresholds or replacing observed PTS with
guessed frame rate, duplicating frames, hiding preview or reducing quality.

Front long gaps start after the first five seconds and persist through the
clip. Prior r4 front reference: 30.001831 fps, maximum gap 45.333 ms, zero >50 ms.
Prelaunch video shape, sensor controls and geometry match that reference.
This is not a controlled same-session kernel A/B: environment/scene differed,
and r5 front reached 79 C versus the prior 75 C. Both used a 1.6 GHz CPU ceiling;
this alone does not exclude thermal, scheduler, capture, conversion, encoder or
storage contention. Root cause is not yet established and no fix is claimed.

Both apps quit normally. Original input/video/sensor geometry and captured
controls were restored in dependency order; user settings/launcher unchanged.
Both sensors and ISP suspended with usage zero. Both device controllers exited
0, but application performance qualification is FAILED, not "test passed".
Independent final audit rehashed 2,214 protected files and all 48 current payload
files; none changed. All 35 private alias targets unchanged, guards active,
no new kernel faults/failed units, PCM closed, no overlay/probe/trace/RTC left.
Auto-lock/DPMS/auto-suspend remain off; rescue default remains unchanged.

Raw media, per-packet/frame data, driver logs and GPU client IDs remain private
on the tablet. No nonzero playback or fresh listening test was requested.
The optional live power/scheduler snapshot arrived after the rear app had
already quit and its process-identity guard refused; it is not live evidence.
An initial final-audit private-log path collision also refused before mutation;
a distinct audit path was used, without overwriting earlier evidence.

Next: locate capture/source/queue/encoder scheduling gaps under full app load,
preserving failed/reference clips. Repeat only with a specific diagnostic or
candidate change; do not treat repeated retries as proof. Physical DMA-fault,
S5, long-run, optics, headset, fresh acoustics and factory-DSP/MTP qualification
remain open. No Android/Windows parity or complete-system claim.

[Scalar failure evidence](tests/mipad2-7.2-r5-recording-regression-summary.json).
[Earlier bounded r5 electrical/native qualification](MIPAD2_R5_DEPLOYMENT_7_2.md).
