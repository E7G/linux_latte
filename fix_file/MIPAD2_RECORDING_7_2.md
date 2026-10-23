# 7.2 camera recording: userspace rational-rate fix, cadence still open

Requested kernel upstream remains `9928c7b8d00c500ee97903afa1cc76c1c36ab2bc`
(7.2.0). Current physical test kernel remains `7.2.0-mipad2-integrated-r3`;
no new kernel C change or build for this userspace defect.

Source fix, reproducible host oracle, pinned three-plugin build and scalar
hardware evidence are published in Snapshot commit
[`806b5ef1baa980c2b6ebacb40eccfe99dc5ae335`](https://github.com/E7G/snapshot/commit/806b5ef1baa980c2b6ebacb40eccfe99dc5ae335) on
`codex/mipad2-7.2-integrated`:
[full report](https://github.com/E7G/snapshot/blob/806b5ef1baa980c2b6ebacb40eccfe99dc5ae335/MIPAD2_VA_FRAME_RATE_7_2.md).

GStreamer VA BRC previously masked native 78125/2604 fps into 12589/2604;
nearest bounded rational packing restores a representable near-30 fps parameter
without changing source caps, PTS, bitrate requests, sensor programming or quality.
The actual generic production parameter dispatcher/helper is exercised under
ASan/UBSan; 384 production cases plus 3969 exhaustive reduced-bound oracle cases.
All 41 combined plugin/AAC/app builder tests pass normally and under Python -O.
An initially stale AAC helper pin was detected by full discovery and corrected.

Same-build 300-frame native video-only comparison: baseline 84.90 Mbps,
27.332 fps, maximum PTS gap 863.667 ms; fixed 15.95 Mbps, 30.002 fps, max 34 ms.
Exact tested plugin and i965 mapped in the process. This validates the scoped
VA bitrate defect, not complete application recording.

**900-frame full-recipe long test still FAILED cadence:** 15.23 Mbps, 29.737 fps,
one 301.333 ms PTS gap at about 20.165 seconds, not startup. No startup frames
excluded. Earlier normal foreground source app with AAC (old plugin) had three
>50 ms intervals in 909 frames, maximum 56.667 ms; its remaining cadence is NOT
proved fixed by the new rational patch. Its old-plugin bitrate already normal.
Raw V4L2 baseline was about 30 fps/max33.889 ms; kernel timestamps represent
buffer completion, not physical sensor SOF. Do not infer frame conservation.

New VA plugins are only privately staged diagnostic artifacts, not installed
into the default launcher/rootfs or promoted as smooth normal-camera recording.
Existing pinned source app/AAC/flash package identities remain their original
historical artifacts; their successful gates are not relabeled as new builds.
Stable GRUB fallback, installed boot/system files, authentication and lock
policy preserved. No audible playback. Camera clients closed; both sensors/ISP
suspended, no kernel fault markers; 686 protected files and 35 private aliases
and bytes unchanged after qualification. Raw video, per-frame metadata/timing,
kernel logs and serial traces remain device-private.

Open gates include attribution/fix of long gaps, normal-app preview/video/audio
and rear-camera validation with matching plugins, optical AE/AWB/focus quality,
7.2 acoustic/UCM, resume/S0I3, S5 cold boot, and failed-reset DMA quiescence.
No complete image, Android/OEM parity or full MiPad2 task completion claimed.

## Later native lifecycle checkpoint

[Measured 7.2 r3 raw-buffer lifecycle and exact scope](MIPAD2_7_2_LIFECYCLE.md)
adds 720p/default and 1080p/NV12 ownership/restart evidence. It does not close
the normal-application recording, optical, audio or long-freeze gates.

## Later normal copied-async checkpoint (7.2 r3)

[Normal front 60-second sample and incomplete rear](https://github.com/E7G/snapshot/blob/511510be29522db307025e6cafa3c5252f302611/MIPAD2_NORMAL_ASYNC_LONG_7_2.md): front1944frames/30.00154fps/max38ms; rear441frames/14.6603s, **requested60s not completed**, stop condition unlabelled. No diagnostic/background/trace capture; no default promotion or new kernel C/build. Previous hard-freeze recovery completed and7.2 restarted; root cause and failed-reset DMA quiescence remain open. Earlier negative recordings are not erased.

## Later rear completion and independent thermal correction

[Normal rear63.841s/1917frames whole-file cadence sample](https://github.com/E7G/snapshot/blob/5124a85963e6ce3b0b95a2d7ea967a5d3883355d/MIPAD2_NORMAL_REAR_LONG_7_2.md) passes30.01206fps/max34.333ms/fullA-Vdecode with no diagnostic/background/trace flags. Prior interrupted rear and556ms normal failure retained; no default promotion or optical/live-preview/Android-parity proof.

[Independent production thermal guard correction](https://github.com/E7G/xiaomi-latte-flash_tools/blob/3806e95ffcf9edcaf3002ece7c8e979b3c9d525f/kernel/THERMAL_GUARD_7_2.md) removes one-state-per-poll upward delay while preserving existing thresholds/ceilings/cooling hysteresis.164hosttests normally/-O; exactsource installed and cool-state checked, not a measured real hot-transition fix. Rearpass predates that change, so cannot be attributed to it. No new kernel C/build/reboot. Previous freeze and failed-reset DMA quiescence stay open.
