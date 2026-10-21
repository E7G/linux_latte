# Mi Pad 2 R26 full-quality recording: scoped RED baseline

Actual device date: 2026-10-21. Kernel 6.14.0-mipad2-integrated-r26,
built source6074419168fbb70aa5685e976874da6cf86d1fae; same boot throughout.
Same R17g app e19702936b2dda4ce0912f073e0e6564c2adc83b / binary SHA256
6298e0b37e28f563a5ee5e97d57edb0c4594cc3dd67cf31334b2422508209c73.
This is new actual H264 evidence, distinct from earlier native720p gates.

## Protocol and unchanged quality

Two30s clips/front+rear each arm, OFF then ON, not randomized. Sole app flag
MIPAD2_CAPTURE_RAW_ASYNC=0/1; native raw direct enabled in both. Real negotiated
1920x1080/30 NV12,1280x720/30 GL preview,15Mbps H264 +192kbps48kHz stereo AAC.
Controlled1.6GHz maximum with original thermal sensors, thresholds, hysteresis
and protection retained; exact480MHz..2240MHz schedutil policies restored after
each arm by finally and independent systemd ExecStopPost. Peak sampled thermal
69/70C OFF,75/75C ON; these are not thermally identical randomized trials.
No resolution/bitrate/fps downgrade, frame dropping, timestamp rewrite, warmup
trimming or quiet removal of bad gaps. Ordinary default-policy/foreground
performance and optical parity remain unproven. No default launcher/GRUB change.

| Arm | Camera | MP4 fps | Maximum PTS gap | Frames | Cadence gate |
|---|---|---:|---:|---:|---|
| OFF | front |29.766882|168.334ms|891|RED|
| OFF | rear |29.977684|75.667ms|901|RED|
| ON | front |29.514684|113.333ms|881|RED|
| ON | rear |29.854615|44.667ms|884|PASS for this clip only|

Gate stays fps>29.5, maximum gap<50ms, no gap>100ms. Both arm-level gates RED.
OFF gaps occur near0.100s/0.230333s front and0.133333s rear. ON front has gaps
near0.100s/0.333667s AND25.957333s; startup-only trimming would conceal a later
51.334ms defect and is not acceptance. Preserve every original clip/report.

## What exact frame joins establish, and what they do not

All3,557 encoder inputs have unique native PTS+offset matches and exact named
route/task witnesses. All source pushes between actual first/last recorded
native endpoints are forwarded; no omitted intermediate native push. Encoder
inputs=outputs=MP4 packets=decoded frames in every clip, zero exact adjacent
decoded repeats; video+AAC decode reports clean. Relative encoder PTS is exact
and mux residual lies within declared333333.333ns tick. This excludes another
downstream loss in these selected recorded epochs, NOT unobserved optical loss
or all frames between user button intent and file boundaries.

Native-push -> encoder-chain arrival median is2.680/3.106ms OFF versus
338.310/334.052ms ON; maxima142.656/165.586ms versus400.889/369.472ms.
These are exact measured stage-arrival wall intervals, not encode completion,
sensor-to-display latency, isolated queue residence, CPU time or causal kernel
speedups. Different historical kernels/cohorts do not form a controlled R26
USB-patch causal comparison. Async4-copy queue remains rejected for default use:
it does not fix both cameras and introduces persistent latency here.

Actual native allocation guard queries remain short:4,362ns OFF/4,503ns ON.
Some OTHER allocations on the source task take198.583/93.123ms in wrapper
zoom/viewfinder negotiation. Same source task executes downstream calls inside
a push: do not mislabel all of them native-pool allocation or a failed guard.
Long CAPS queries/events still overlap recording-gap windows. Timing nesting
and off-CPU observations do not identify a unique lock or prove all wall time
is compulsory work. Next optimization should target demonstrated negotiation
and downstream backpressure, not increase queues or forge constant timestamps.

Zero-VB2-driver-owned overlap is252.548/52.610ms OFF and8.531665/7.370520s ON.
The latter rear clip passes cadence despite7.37s zero-owned overlap. Thus this
counter alone does NOT prove physical CSS starvation or sensor frame loss.
One ON source anomaly is not confirmed as the same adjacent encoded pair;
its non-match is retained. Global preview/thumbnail calls right-censored by app
exit remain explicit; selected recorded data calls have no unfinished interval.

## Harness corrections, retained original failures

Two preliminary OFF-only runs aborted, closed normally and preserved evidence.
First required ffprobe r_frame_rate30/1, but the actual negotiated full-size
caps are30/1 while the file's guessed representational base is120/1. FFmpeg
documents that field as a guessed base capable of representing timestamps,
not measured capture rate. Second correctly validates real caps but exposed a
missing scalar samples field in the thermal/storage projector. Neither abort
was reclassified as successful or used for a complete crossover claim.

Fresh v3 adds explicit scalar thermal/CPU/storage samples and checks actual
full-size/preview30fps caps, GL path, requested bitrates and file codecs/sizes.
Four host dry runs execute the entire two-cycle/finalizer for both arms with
PASS and RED cadence fixtures, using the real projector; no hardware calls.
Transport tests accept ffprobebase120 with real30caps, reject720p/15fps/missing
requested AAC bitrate, and keep private journal/graph/metadata/error details
tablet-local. Named-tail analyzers pass38 Linux tests in both normal and-O mode.
All12 original six-stage real-data analyses finish0. Raw media, syscall pointer
arguments, ownership tables, binary traces and individual pixel hashes stay
tablet-private; public JSON contains explicit scalar/structural aggregates.

## RTC, restoration and remaining scope

Both post-recording10s RTC cycles restore functional operation; actual S0I3
deltas are0 OFF and9,763,328us ON. The managed serial collector runs until outer
finally; inherited PM helper serial_expected_open=false is inaccurate lifetime
metadata, NOT proof the collector was stopped. Exact host USB handle state
inside suspend is not asserted. Keep the zero and positive counterexample:
active-debug residency is intermittent, not fixed/proven by the R26 USB halt
error-path backport. Current boot has four tested RTC cycles, not just the two
earlier native/silent-electrical cycles.

All owned camera/serial controllers terminal, original settings/controls restored,
sensors+ISP usage0/suspended, thermal guard+anti-idle active, no runtime cap
dropin, GPU200..600MHz, no trace instances/kprobes, saved GRUBbqdiag1 unchanged.
Read-only whole-boot selected BUG/WARNING/Oops/GPU-HANG/T4KA3-ID-NACK/stop-timeout
counts all0. No reboot or audible tones.43 scalar aliases checked byte-for-byte,
37user-readable/six originally restricted permissions unchanged. New43-entry
private restoration manifest supplements, never overwrites, old35-entry one.

Full recording smoothness, ordinary power/foreground UX, optical AE/WB/focus,
physical DMA/reset fencing, S5 cold reliability and complete flash/OEM parity
remain OPEN. This commit changes documentation/evidence only; no performance
fix or stable-default promotion is claimed. See
tests/mipad2-r26-recording-validation-summary.json.

Primary semantics:
- https://ffmpeg.org/doxygen/trunk/structAVStream.html
- https://gstreamer.freedesktop.org/documentation/coreelements/queue.html
