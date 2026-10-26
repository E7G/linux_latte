# SPDX-License-Identifier: GPL-2.0
import struct
import unittest
import mipad2_native_gst_trace as trace

def blob(rows=None, **header):
    if rows is None:
        rows = [(1000000, 2000, 33333333, 0, 1, 3110400, 2000000, 1, 0, 0, 0)]
    values = dict(pid=123, count=len(rows), dropped=0, sources=1, errors=0)
    values.update(header)
    data = bytearray(trace.SIZE)
    trace.HEADER.pack_into(data, 0, b'MP2V4F01', 1, 88, 4096,
                           values['pid'], values['count'], values['dropped'],
                           values['sources'], values['errors'])
    for i, row in enumerate(rows):
        trace.RECORD.pack_into(data, 64 + i * 88, *row)
    return data

class NativeFrameTraceTests(unittest.TestCase):
    def test_valid_bounded_metadata(self):
        decoded = trace.decode(blob())
        self.assertEqual(decoded['count'], 1)
        self.assertEqual(decoded['pid'], 123)

    def test_raw_and_adjusted_offsets_remain_distinct(self):
        row = trace.decode(blob())['rows'][0]
        self.assertEqual(row['driver_offset'], 0)
        self.assertEqual(row['output_offset'], 1)
        self.assertEqual(trace.summarize(trace.decode(blob()))['groups'][0]
                         ['raw_vs_output_offset_changes'], 1)

    def test_overflow_and_errors_are_not_silent(self):
        for header in [dict(dropped=1), dict(errors=1), dict(count=4097),
                       dict(count=0), dict(sources=2), dict(pid=0)]:
            with self.subTest(header=header), self.assertRaises(ValueError):
                trace.decode(blob(**header))

    def test_bad_lengths_and_trailing_data(self):
        with self.assertRaises(ValueError):
            trace.decode(blob()[:-1])
        data = blob()
        data[-1] = 1
        with self.assertRaises(ValueError):
            trace.decode(data)

    def test_bad_header_version_and_magic(self):
        for start, value in [(0, b'INVALID!'), (8, struct.pack('<I', 2)),
                             (12, struct.pack('<I', 80)),
                             (16, struct.pack('<Q', 4000))]:
            data = blob()
            data[start:start + len(value)] = value
            with self.assertRaises(ValueError):
                trace.decode(data)

    def test_padding_difference_does_not_invent_payload_identity(self):
        k = dict(state=5, minor=0, sequence=0, timestamp_ns=1000999,
                 exp_id=0, bytesused=3112960)
        result = trace.join_kernel(trace.decode(blob()), [k])
        self.assertEqual(result['exact_kernel_matches'], 1)
        self.assertEqual(result['matched_zero_CSS_IDs'], 1)
        self.assertFalse(result['payload_equality_claimed'])
        self.assertFalse(result['physical_sensor_or_encoder_MP4_conservation_proved'])

    def test_missing_and_ambiguous_kernel_keys_rejected(self):
        k = dict(state=5, minor=0, sequence=0, timestamp_ns=1000999,
                 exp_id=1, bytesused=3112960)
        for records in [[], [k, k], [dict(k, state=6)],
                        [dict(k, sequence=1)], [dict(k, minor=1)]]:
            with self.subTest(records=records), self.assertRaises(ValueError):
                trace.join_kernel(trace.decode(blob()), records)

    def test_invalid_raw_timestamp_and_source(self):
        for index, value in [(0, trace.NONE), (0, 1000001), (3, trace.NONE),
                             (7, 0), (10, 2), (5, 0)]:
            row = list(trace.RECORD.unpack_from(blob(), 64))
            row[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                trace.decode(blob([row]))

    def test_duplicate_identity_rejected(self):
        row = trace.RECORD.unpack_from(blob(), 64)
        with self.assertRaises(ValueError):
            trace.decode(blob([row, row]))

    def test_observed_epoch_reset_is_not_a_fabricated_sequence(self):
        first = list(trace.RECORD.unpack_from(blob(), 64))
        second = first.copy()
        second[0] = 2000000
        second[6] = 3000000
        second[8] = 1
        decoded = trace.decode(blob([first, second]))
        self.assertEqual(len(trace.summarize(decoded)['groups']), 2)
        self.assertEqual([r['driver_offset'] for r in decoded['rows']], [0, 0])

if __name__ == '__main__':
    unittest.main()
