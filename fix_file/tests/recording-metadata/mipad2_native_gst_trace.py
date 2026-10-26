# SPDX-License-Identifier: GPL-2.0
"""Decode bounded metadata only; never read camera pixels."""
import collections, hashlib, struct
HEADER = struct.Struct('<8sII6Q')
RECORD = struct.Struct('<11Q')
FIELDS = ['driver_ns', 'pts_ns', 'duration_ns', 'driver_offset', 'output_offset', 'bytes', 'monotonic_ns', 'source_id', 'epoch', 'flags', 'bad_timestamp']
SIZE = 64 + 4096 * 88
NONE = 2 ** 64 - 1

def decode(blob):
    if len(blob) != SIZE:
        raise ValueError('Wrong trace allocation length')
    magic, version, recordsize, capacity, pid, count, dropped, sources, errors = HEADER.unpack_from(blob)
    if (magic, version, recordsize, capacity) != (b'MP2V4F01', 1, 88, 4096) or not 0 < count <= capacity or (not 0 < sources <= count) or (not pid):
        raise ValueError('Trace header contract')
    if dropped or errors:
        raise ValueError('Metadata trace loss or producer errors')
    rows = []
    seen = set()
    last = {}
    for i in range(count):
        r = dict(zip(FIELDS, RECORD.unpack_from(blob, 64 + i * 88)))
        if not (r['driver_ns'] and r['driver_ns'] != NONE and (r['driver_ns'] % 1000 == 0) and (r['driver_offset'] < 2 ** 32) and (r['pts_ns'] != NONE) and (r['output_offset'] != NONE) and (0 < r['bytes'] <= 24 * 1024 ** 2) and (r['monotonic_ns'] >= r['driver_ns']) and (1 <= r['source_id'] <= sources) and (r['bad_timestamp'] in [0, 1])):
            raise ValueError('Frame metadata bounds')
        key = (r['driver_offset'], r['driver_ns'])
        if key in seen:
            raise ValueError('Repeated native identity')
        seen.add(key)
        group = (r['source_id'], r['epoch'])
        prior = last.get(group)
        if prior and (r['driver_ns'] <= prior['driver_ns'] or r['driver_offset'] <= prior['driver_offset'] or r['monotonic_ns'] < prior['monotonic_ns']):
            raise ValueError('Nonmonotonic source/epoch')
        last[group] = r
        rows.append(r)
    if any(blob[64 + count * 88:]):
        raise ValueError('Unexpected trailing records')
    return dict(pid=pid, rows=rows, sources=sources, count=count, sha256=hashlib.sha256(blob).hexdigest())

def summarize(d):
    rows = d['rows']
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['source_id'], r['epoch']].append(r)
    out = []
    for (source, epoch), rs in sorted(groups.items()):
        delta = [b['driver_ns'] - a['driver_ns'] for a, b in zip(rs, rs[1:])]
        out.append(dict(source_id=source, observed_epoch=epoch, records=len(rs), driver_fps=(len(rs) - 1) * 1000000000.0 / (rs[-1]['driver_ns'] - rs[0]['driver_ns']) if len(rs) > 1 else None, driver_sequence_gaps=sum((b['driver_offset'] != a['driver_offset'] + 1 for a, b in zip(rs, rs[1:]))), driver_gaps_above50ms=sum((x > 50000000 for x in delta)), raw_vs_output_offset_changes=sum((r['driver_offset'] != r['output_offset'] for r in rs)), bad_timestamp_rows=sum((r['bad_timestamp'] for r in rs)), buffer_sizes=sorted({r['bytes'] for r in rs})))
    return dict(pid=d['pid'], records=d['count'], sources=d['sources'], groups=out, private_raw_sha256=d['sha256'], native_GStreamer_metadata_only=True, pixels_inspected=False, encoder_or_recording_qualification=False)

def join_kernel(d, trace, minor=0):
    bykey = collections.defaultdict(list)
    for r in trace:
        if r['state'] == 5 and r['minor'] == minor:
            bykey[r['sequence'], r['timestamp_ns'] // 1000 * 1000].append(r)
    matched = []
    sizes = collections.Counter()
    for r in d['rows']:
        candidates = bykey[r['driver_offset'], r['driver_ns']]
        if len(candidates) != 1:
            raise ValueError('Missing or ambiguous kernel completion -> Gst source identity')
        k = candidates[0]
        matched.append(k)
        sizes[k['bytesused'], r['bytes']] += 1
    return dict(Gst_source_records=len(d['rows']), exact_kernel_matches=len(matched), identity_fields=['video minor', 'raw V4L2 sequence before Gst offset adjustment', 'floor(kernel timestamp_ns/1000)*1000 == raw driver timestamp_ns'], matched_zero_CSS_IDs=sum((r['exp_id'] == 0 for r in matched)), matched_nonzero_CSS_IDs=sum((r['exp_id'] != 0 for r in matched)), kernel_vs_Gst_payload_size_pairs=[dict(kernel_bytes=k, Gst_bytes=g, frames=n) for (k, g), n in sorted(sizes.items())], payload_equality_claimed=all((k == g for k, g in sizes)), CSS_EOF_correspondence_proved=False, physical_sensor_or_encoder_MP4_conservation_proved=False)

def selftest():
    blob = bytearray(SIZE)
    HEADER.pack_into(blob, 0, b'MP2V4F01', 1, 88, 4096, 123, 1, 0, 1, 0)
    RECORD.pack_into(blob, 64, 1000000, 2000, 33333333, 0, 5, 16, 2000000, 1, 0, 0, 0)
    d = decode(blob)
    assert d['rows'][0]['driver_offset'] == 0 and d['rows'][0]['output_offset'] == 5
    k = dict(state=5, minor=0, sequence=0, timestamp_ns=1000999, exp_id=0, bytesused=32)
    a = join_kernel(d, [k])
    assert a['exact_kernel_matches'] == 1 and (not a['payload_equality_claimed']) and (a['matched_zero_CSS_IDs'] == 1)
    bad = []
    for offset, value in [(0, b'BADMAGIC'), (16, struct.pack('<Q', 4095)), (32, struct.pack('<Q', 4097)), (40, struct.pack('<Q', 1)), (64, struct.pack('<Q', 1000001)), (64 + 7 * 8, struct.pack('<Q', 0))]:
        x = bytearray(blob)
        x[offset:offset + len(value)] = value
        bad.append(bytes(x))
    bad.append(bytes(blob[:-1]))
    x = bytearray(blob)
    x[-1] = 1
    bad.append(bytes(x))
    for data in bad:
        try:
            decode(data)
        except ValueError:
            continue
        raise AssertionError('Malformed metadata accepted')
    for trace in [[], [k, k]]:
        try:
            join_kernel(d, trace)
        except ValueError:
            continue
        raise AssertionError('Missing/ambiguous kernel key accepted')
    return dict(valid_metadata_and_padding_mismatch_case=1, negative_controls=len(bad) + 2, raw_offsets_preserved_before_rewrite=True)
if __name__ == '__main__':
    import json
    print(json.dumps(selftest()))
