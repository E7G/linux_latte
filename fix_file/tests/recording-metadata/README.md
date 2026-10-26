# Strict recording metadata arrival analysis

Run `python3 -m unittest -v` and `python3 -O -m unittest -v` here: 55 tests.

Input is decoded control-call intervals and exact encoder-input PTS/offset keys selected within qualified nonempty EOS epochs. Raw traces, ownership tables and pixels are not published. No frame fitting, trimming or assumed synchronous source/encoder call. Queue sink-arrival to worker-begin includes blocked enqueue, not isolated residence. See ../../MIPAD2_R17H_CURRENT_CAPS_DEVICE.md.

## Native completion to GStreamer source metadata

`mipad2_native_gst_trace.py` decodes the bounded opt-in V4L2 observer. The helper
`gstv4l2src_native_frame_trace.inc` writes fixed-size metadata to a precreated
0600 regular tmpfs file, never pixels or buffer contents. The private source
recipe `instrument_mipad2_native_trace.py INPUT OUTPUT` accepts only the exact
GStreamer 1.28.7 source SHA; removing instrumentation recovers it byte-for-byte.
Build this only as an isolated plugin, not a global replacement. Set
`MIPAD2_V4L2_NATIVE_FRAME_TRACE` to the precreated 360512-byte tmpfs path, and
read/copy/hash it only after the producer exits and no mapping remains.

Raw V4L2 timestamps/sequences must be captured BEFORE GStreamer adjustment.
The r6 preview test observed 490 unique kernel/source matches, with output
offset minus raw sequence equal to +1 for 489 frames; one startup frame retained
zero. Kernel payload was 3112960 bytes, Gst size 3110400 bytes: size inequality
is not a lost frame or permission to invent padding contents. No payload was read.

In an 8-second accepted-ISYS subset, 241 EOF IDs each matched one kernel/source
chain within an explicit 500ms candidate bound. Two matching completions occurred
after the sampler window ended; clipping both sides to that window would falsely
lose them. IDs and temporal bounds still do NOT account for physical sensor SOFs.
This is instrumented preview evidence, not recording/encoder/MP4/OEM cadence proof.
Original stale-guard preparation/cleanup failures remain preserved separately.
See ../mipad2-7.2-r6-native-Gst-summary.json. New decoder adds 10 unittest methods
to the preexisting 45; run normal and `-O` modes.
