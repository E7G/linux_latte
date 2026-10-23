# MiPad2 7.2 r4: normal encoded recording and resume regression

## Status (2026-10-24, CONT23–24)

The same full `7.2.0-mipad2-integrated-r4` image (source
`69bb7d3fbea73093bed7b7bcf060472ecb5bfea0`) passed two real normal-foreground
Snapshot recordings, followed by a 12-second RTC resume and native camera reopen
tests. No new production driver change, image replacement or reboot in CONT24.
This is bounded regression evidence, not full Android/Windows parity or proof
that every reported long-run/visual symptom is fixed.

## Normal app recordings: unchanged full quality

Snapshot runtime build `0a7ce87affa9`, RAW_ASYNC=1, existing VA framerate plugin
and i965 backend. New private settings/output directories preserved real user
preferences and the installed launcher. Diagnostic actions, background capture
and per-frame V4L2 tracing were disabled. Actual foreground focus, owning PID and
selected sensor were checked before ordinary keyboard start/stop. The rear
camera was selected through its actual visible normal Switch Camera control.

Only the requested measurement window changed to 30 seconds to preserve the
2 GiB root-space floor. Resolution, bitrate policy, encoder, queue profile and
quality were not lowered. Extra file time includes normal shortcut/stop checks.

| Camera | PTS span (s) | Decoded frames | Actual PTS fps | Max gap (ms) | Video bitrate | Peak record temp |
|---|---:|---:|---:|---:|---:|---:|
| front | 32.764667 | 984 | 30.001831 | 45.333 | 14719217 | 75 C |
| rear | 33.020333 | 992 | 30.011811 | 34.667 | 14904814 | 78 C |

Both files contain 1920×1080 H.264 (no B frames) and 48 kHz stereo AAC. Packet PTS
were strictly increasing, with no gaps above 50 ms. Full video and audio decode
passed, decoded frame counts equalled video packet counts, and no adjacent exact
decoded-image repeats occurred. Cadence uses actual packet PTS, not guessed
`r_frame_rate`. This does not measure conservation of every incoming sensor frame
or controlled optical/preview-presentation quality. Observed CPU frequency limits
were 1.6 GHz; thermal guard remained active. Short clips do not qualify long-run
thermal behavior; recorded peaks of 75/78 C are retained, not hidden.

The same recording process showed positive **video engine** fdinfo deltas
(14979144400 / 15776248800 ns), excluding video-enhance engines and deduplicating
shared client IDs. Read-only samples include newly opened clients and retain
maximum cumulative values. This independently observes process GPU video-engine
work; library maps alone are weaker evidence, and neither identifies the exact
GStreamer encoder factory. No pointer/per-client/per-frame/raw media was exported.
Method references: [kernel DRM client statistics](https://www.kernel.org/doc/html/latest/gpu/drm-usage-stats.html),
[GStreamer VA H.264 encoder](https://gstreamer.freedesktop.org/documentation/va/vah264enc.html).

## Camera ownership and post-recording resume

Before normal recordings, and again after normal recordings plus RTC resume,
each camera completed four 120-frame native 1080p NV12 phases: same-owner
streamoff/on, a separate observer's four expected EBUSY operations, and final
owner close/reopen. Total 1920 native frames across the two separate datasets,
with no sequence discontinuities, buffer errors or new kernel fault markers.
These native frames are separate from the 1976 decoded normal-recording frames.
Physical failed-reset/DMA-quiescence fault injection was not performed.

The post-recording 12-second RTC test added **12321568 us** of S0I3 residency (OS estimate 11.746915 s). The same boot resumed, both sensors/ISP returned to runtime-suspended usage 0,
and actual RT5659 0x65=0x0040 plus both TFA status=0xd85f remained correct after
resume and during digital-zero PCM. No runtime route overlays, forced register
writes, cache replay or resume repair script. Filtered trace includes PLL off
then on, not a PLL forced on throughout sleep. USB attached; shared wake IRQ9
does not uniquely identify the source or qualify untethered idle consumption.

The [exact tested r4 fixture](tests/mipad2-7.2-r4-lifecycle-device-test.c) was
compiled with `-O2 -std=gnu11 -Wall -Wextra -Werror`. Its strict uname guard
requires r4. The historical first reuse of the r3-bound fixture exited 2 before
opening the camera; that failed receipt remains retained. Controller format
writes had already happened, so explicit restoration was required. Another
retained restoration audit showed exposure being adjusted by a later blanking
write. Current controllers restore CROP before FORMAT and BLANKING separately
before EXPOSURE, then independently verify all captured values. Never reuse the
old r3 binary on r4 or silently call the failed attempt a pass.

## Recording audio and orientation are not acoustic/optical qualification

AAC decoded finite nonzero samples with no clipping, but ambient RMS was only
about -78/-75 dBFS. No controlled sound source or human listening test was used.
Post-test default source was IntMic, not a monitor, unmuted at 100%; no levels
were changed. This is not microphone sensitivity/SNR/channel-quality validation.
Raw decoded PCM existed only in RAM. Neither test file reported a nonidentity
display-rotation side-data entry; no controlled device pose or visual playback
verification was performed, so orientation is not marked passed or failed.

## Cleanup, final state and open work

The first rear launch was gated by the 96 MiB staging margin before app/config
creation (the 2 GiB hard floor was still met). Only seven superseded test cache
directories were removed: 28102319 logical bytes. Current normal/front caches
were hash-preserved. No recordings, photos, logs or installed kernels deleted.
Both new clips remain device-private as latest evidence. No raw UART/kernel/
ftrace/per-frame data on the host or in this report.

After the final tests, all app/test units were terminal, PCM closed, RTC cleared,
temporary probes and trace instances removed, 2163 protected installed files and
35 private aliases byte-identical. Deep fresh checks matched original input,
video format, both sensor crop/format and captured controls against BOTH app
snapshots. Rescue default unchanged; auto-lock/DPMS/automatic suspend remain off
as requested; thermal/no-idle guards active. No new kernel fault markers.

Open: controlled optical/rotation/mic/headphone/stereo listening, sustained
recording/thermal/preview-presentation behavior, the earlier multi-hour hang and
physical failed-reset DMA work, S5 reliability, idle C2C audio power, factory
DSP/UCM/calibration-MTP policy and full OEM equivalence. No full OS image built.

[Scalar evidence](tests/mipad2-7.2-r4-camera-recording-summary.json).
[Full r4 build/deployment](MIPAD2_R4_DEPLOYMENT_7_2.md).
