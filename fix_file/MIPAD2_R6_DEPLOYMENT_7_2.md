# Mi Pad 2 Linux 7.2 r6: deployment and native completion tracing

Tested 2026-10-26. Complete matching-release kernel, 31 CMS-verified modules,
unchanged r5 config; one serial-guarded warm one-shot boot succeeded. Kernel and
initramfs remain on the root Btrfs filesystem, not the nearly full ESP. The saved
recovery default is unchanged. This is not S5 cold-start or OEM parity proof.

## Qualified scope

- First-probe smoke: 51 checks, both sensors and VCM natively bound. No reprobe,
  GPIO/PMIC test writes, temporary routing overlay or forced module ABI.
- Tracing disabled: front/rear native 1920x1080 NV12, four stream lifecycle phases
  per camera, 120 dequeued buffers per phase (960 total), approximately 30 fps,
  no sequence discontinuities/buffer errors. Fresh input, crop, format, blanking
  and exposure restored; sensors/ISP settled suspended with usage zero.
- Dedicated diagnostic trace: 992 events, 960 DONE and 32 ERROR queue flushes,
  zero trace overruns/loss. All 960 native DQBUF records matched exactly once by
  video minor, sequence, buffer index, payload size and the existing timestamp
  truncated from nanoseconds to V4L2 microseconds. No pixel data were inspected.
- **CSS ID zero is not restricted to ERROR:** eight zero IDs occurred in DONE,
  exactly the sequence-0 buffer of each camera/stream phase. Remaining 952
  matches had nonzero IDs. Keep zero IDs opaque; do not synthesize replacements
  or claim complete ISYS-to-CSS correspondence. Original stricter parser failure
  remains preserved. Offline reanalysis used the same private data, no recapture.
- A 12-second RTC s2idle cycle after camera use returned without new fault
  markers; estimated suspended time 11.954 seconds, PMC S0I3 delta 12.536 seconds.
  USB serial remained attached; not pristine untethered sleep/power qualification.
- After resume, a separate untraced native lifecycle repeated all 960 buffers
  with no sequence gaps/errors; input, sensor state and runtime PM restored again.
- The canonical command-line tool was run on the same existing private trace and
  CSVs, reproducing 960 exact matches and eight explicitly unqualified zero IDs.

## Reproduce metadata analysis locally on the device

`fix_file/tests/mipad2-atomisp-buffer-trace-join.py --selftest`

For private existing traces, pass `--trace TRACE --native rear:CSV --native
front:CSV`. Defaults require 120 frames in each of four phases; specify the actual
profile with `--frames`/`--phases`. The tool emits scalar aggregates only, never
raw events. Its parser/matcher functions are AST-identical to those exercised on
the 960-frame private trace. Eight malformed/duplicate/ambiguous/mismatched input
negative controls are rejected; zero IDs remain explicitly unqualified for CSS
correspondence. Per-subset extra DONE entries can belong to the other camera;
only the union accounts for the full capture.

Keep raw metadata/camera samples and full kernel logs device-private. Enable the
event only in a bounded dedicated ftrace instance, check loss statistics, then
disable/remove that instance and verify global tracing settings are unchanged.
Do not bypass cache maintenance, thermal/memory guards or recording quality.

## Still open

Native DQBUF identity is not physical sensor frame conservation or encoder/MP4
identity. No recording cadence fix, 30-second normal UI/endurance gate, new sound
listening test, optical quality or full Android/Windows parity is claimed here.
The new tracepoint is observability, disabled by default, not a pacing workaround.
The measured tracepoint-to-buffer timestamp difference is not CPU cost or sensor
latency. See `tests/mipad2-7.2-r6-deployment-summary.json` for scalar evidence.
