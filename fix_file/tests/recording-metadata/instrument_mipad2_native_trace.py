#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Produce an isolated observer from the exact GStreamer 1.28.7 source."""
import argparse
import hashlib
from pathlib import Path

BASELINE_SHA256 = 'fa5e65d80eefd77f14a3a395395aff0b55e93b166239a84207d2d5f5c9a7ed0a'


def instrument(original, helper):
    if hashlib.sha256(original.encode()).hexdigest() != BASELINE_SHA256:
        raise ValueError('Expected the exact qualified GStreamer 1.28.7 source')
    nl = chr(10)
    marker = ('static GstFlowReturn' + nl +
              'gst_v4l2src_create (GstPushSrc * src, GstBuffer ** buf)')
    edits = [
        (marker, helper + nl + marker),
        ('  GstClockTime delay;', '  GstClockTime delay;' + nl +
         '  GstClockTime mp2_native_driver_ns;' + nl +
         '  guint64 mp2_native_driver_offset;'),
        ('  timestamp = GST_BUFFER_TIMESTAMP (*buf);',
         '  timestamp = GST_BUFFER_TIMESTAMP (*buf);' + nl +
         '  mp2_native_driver_ns = timestamp;' + nl +
         '  mp2_native_driver_offset = GST_BUFFER_OFFSET (*buf);'),
        ('  GST_BUFFER_DURATION (*buf) = duration;',
         '  GST_BUFFER_DURATION (*buf) = duration;' + nl +
         '  mp2_native_frame_trace (GST_OBJECT (src), *buf, mp2_native_driver_ns,' + nl +
         '      mp2_native_driver_offset, v4l2src->has_bad_timestamp);'),
    ]
    result = original
    for before, after in edits:
        if result.count(before) != 1:
            raise ValueError('Instrumentation anchor is not unique')
        result = result.replace(before, after)
    recovered = result
    for before, after in reversed(edits):
        if recovered.count(after) != 1:
            raise ValueError('Instrumentation cannot be removed exactly')
        recovered = recovered.replace(after, before)
    if recovered != original:
        raise ValueError('Non-observer source change detected')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output exists: never overwrite a source or prior candidate')
    helper = Path(__file__).with_name('gstv4l2src_native_frame_trace.inc').read_text()
    result = instrument(args.input.read_text(), helper)
    with args.output.open('x') as output:
        output.write(result)
