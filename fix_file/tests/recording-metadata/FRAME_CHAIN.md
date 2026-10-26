# Optional, bounded frame-chain metadata observer

`gstmp2_frame_chain.c` is a private opt-in GStreamer tracer, not an installed
camera fix. Build against the target's GStreamer development files:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -shared -fPIC \
  gstmp2_frame_chain.c -o libgstmp2control.so \
  $(pkg-config --cflags --libs gstreamer-1.0)
```

Use a private plugin directory/registry, `GST_TRACERS=mipad2-control`, an exclusive
absolute `MIPAD2_CONTROL_FILE`, `MIPAD2_CONTROL_PID` set to the actual application
PID before `gst_init`, and bounded `MIPAD2_CONTROL_CAPACITY`. Avoid overriding the
daily system plugin directory. The tracer does not activate for an inherited
foreign PID. It reads scalar metadata, not pixel payloads; it does not map/ref
buffers or modify flow, timestamps, cadence, cache coherency, or quality.

ABI4 contains a 64-byte header, 512 dictionary slots of 512 bytes, then capacity
records of 128 bytes. Records include monotonic observation time, PTS/DTS,
offset, duration, size, thread/object IDs, operation/result and complete SEGMENT
fields. Actual factory names come from `gst_element_get_factory`, not class-name
guesses. Inspect only after the producer exits. A 262144-record allocation is
33816640 bytes; a real 30-second recording exceeded the smaller 131072-record
allocation. Overflow or uncommitted slots invalidate complete-trace claims.

`mipad2_frame_chain.py` decodes ABI4; `mipad2_frame_chain_join.py` provides strict
ordered identity joins, restricted observed unit-rate TIME-segment conversion,
and explicit rational time-base quantization. No closest-frame search, fitted
offset, arbitrary tolerance, frame trimming, or guessed nominal FPS is used.
Unsupported segment formats/rates are rejected. Import these helpers in a
private analysis controller; do not publish raw trace rows or recordings.

Hook result types differ: `pad-send-event-post` reports `GstFlowReturn` (OK=0),
while `pad-push-event-post` reports `gboolean` (TRUE=1). Use the matching contract.
Source references:
- [GstSegment API](https://gstreamer.freedesktop.org/documentation/gstreamer/gstsegment.html)
- [GStreamer 1.28.7 gstpad.c](https://github.com/GStreamer/gstreamer/blob/1.28.7/subprojects/gstreamer/gst/gstpad.c)
- [GStreamer 1.28.7 gstsegment.c](https://github.com/GStreamer/gstreamer/blob/1.28.7/subprojects/gstreamer/gst/gstsegment.c)
- [GStreamer 1.28.7 qtmux](https://github.com/GStreamer/gstreamer/blob/1.28.7/subprojects/gst-plugins-good/gst/isomp4/gstqtmux.c)

## Qualified scope, Mi Pad 2 r6

An opt-in 1080p NV12/H.264 15 Mbps/AAC 192 kbps normal-UI recording used the
actual `vah264enc` and `qtmux` factories. All 1317 native-source observations
matched source-pad metadata; the contiguous 926-frame recording subset matched
926 encoder inputs, 926 encoder outputs and 926 mux video inputs. All 926 MP4
packet PTS and sizes matched observed segment conversion plus the actual
1/3000 time base. Segment conversion was cross-checked 2781 times against the
target's actual GStreamer API. No extra frame loss appeared between completed
native source and MP4 in this case.

This is NOT a cadence fix: 17 intervals exceeded 50 ms, already present in native
driver timestamps. Playback/decode success is not proof of physical sensor frame
conservation, pixel equality, an uninstrumented baseline, causal backpressure,
or Android/Windows parity. All four selected recording boundaries had paired
calls, but 50 unmatched pre-hooks elsewhere in the complete process trace remain
explicitly outside that statement. Do not infer complete global call pairing
from complete trace storage. Failed earlier overflow and event-parser receipts
were retained rather than relabelled.

Run portable format/identity tests normally and with optimized Python:

```sh
python3 -m unittest discover -s . -p 'test_mipad2_frame_chain*.py'
python3 -O -m unittest discover -s . -p 'test_mipad2_frame_chain*.py'
```
