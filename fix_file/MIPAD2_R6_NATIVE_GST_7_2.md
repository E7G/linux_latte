# r6 native kernel to GStreamer preview identity

2026-10-26, controlled Mi Pad 2 Linux 7.2 r6. This is metadata-only,
instrumented preview evidence, not an encoding improvement or OEM qualification.

## Source and observer qualification

The private observer is derived from the byte-pinned official GStreamer 1.28.7
[v4l2src source](https://github.com/GStreamer/gstreamer/blob/1.28.7/subprojects/gst-plugins-good/sys/v4l2/gstv4l2src.c),
SHA256 `fa5e65d80eefd77f14a3a395395aff0b55e93b166239a84207d2d5f5c9a7ed0a`.
Removing instrumentation recovers that source exactly. The portable recipe in
`tests/recording-metadata/instrument_mipad2_native_trace.py` reproduces the
hardware-tested instrumented source byte-for-byte. It will reject a different
baseline rather than guess whether anchors still have equivalent semantics.

The helper records only bounded buffer metadata in a caller-precreated tmpfs
file (4096 records, 88 bytes each, 64-byte header). No pixels, pointers or payload
padding are read. It does not change buffer metadata, timestamps, offsets,
cache maintenance, stream control, flow returns or encoder settings. Six C test
cases exercised disabled/enabled operation, overflow and observed reset, buffer
immutability and file rejection checks. Decoder functions are AST-identical to
the actual private-data analysis; 55 host unittest methods pass normally and
under Python `-O` (45 earlier plus 10 native-observer tests).

Build used host GStreamer 1.28.4 headers and GLib 2.88.3; actual loading/factory
selection was checked against tablet GStreamer 1.28.7. This is not a claim of an
exact-version SDK build. The plugin was isolated to the test launcher, and the
global video4linux2 plugin/default camera launcher remained unchanged.

## Actual results

- First attempt captured 419 source records and exactly matched every one to a
  kernel DONE buffer by raw sequence and original driver timestamp. Cleanup
  failed because a nested legacy helper still asserted the previous r5 boot ID;
  its controlled owned-stop path closed the app. A separate guarded recovery
  restored fresh original format/crop/blanking/exposure and checked runtime PM.
  That failed result was preserved, not relabelled as a successful normal Quit.
- A distinct corrected run reset inherited restore flags before launch and
  recursively checked all embedded boot/release guards. It captured **490/490**
  unique kernel-to-Gst matches at approximately 30.007 fps, no source sequence
  gaps, no source intervals above 50ms and no bad-driver-timestamp fallback.
  Normal UI Quit, actual fresh controls/geometry restoration, camera release,
  trace-instance removal and unchanged global tracing settings all passed.
- One startup CSS ID was zero; 489 were nonzero. Zero IDs are kept opaque.
- Kernel payload was 3112960 bytes while Gst exposed 3110400 bytes, consistently
  2560 bytes less. No payload identity is claimed solely from metadata, nor are
  padding bytes synthesized to make the sizes equal.
- Post-adjustment Gst offset was raw V4L2 sequence +1 for 489 records; one startup
  record had difference zero. Raw sequence MUST be captured before adjustment;
  treating final Gst offset as the native sequence would invent a startup gap.
- In the 8.027-second accepted-ISYS sampler window, 241 EOF events were joined by
  nonzero CSS ID plus an explicit 500ms candidate distance to unique kernel and
  source records in the FULL trace. No candidate was missing or ambiguous. Two
  matched completions occurred after the sampler window ended. Clipping both
  sides to that window would lose them despite equal in-window event counts.
- Observed kernel completion followed EOF by 55.35-56.56ms. Source observer time
  after the driver buffer timestamp was 0.117-1.354ms (median 0.364ms), not pure
  CPU time. Driver-to-Gst-PTS translation varied by 8811ns in this preview.

Raw camera/event/kernel data remain private on the tablet; source/scalar summaries
only are tracked. See `tests/mipad2-7.2-r6-native-Gst-summary.json`.

## Open work

Accepted-ISYS EOF is not physical sensor SOF accounting. Normal preview at 30 fps
does not prove the encoder or MP4 recorder preserves every frame. No recording
cadence, audio listening, optical quality, endurance or Android/Windows parity
gate is claimed. Next correlate these native/source identities with actual
encoder input/output and muxer timestamps under the unchanged normal UI quality
profile, preserving thermal/memory/free-space/coherency guards.
