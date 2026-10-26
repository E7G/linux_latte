"""Strict ABI4 scalar tracer decoder; inspect only after producer exit."""
import collections
import math
import struct
from pathlib import Path

HEADER = struct.Struct('<8sII6Q')
RECORD = struct.Struct('<5Q2IiI9Q')
DATA_START = 64 + 512 * 512
PAIRS = {1: 2, 3: 4, 6: 7, 8: 9, 10: 11, 12: 13, 14: 15}
KINDS = {1: 'push', 3: 'chain', 6: 'push-event', 8: 'pad-query',
         10: 'state', 12: 'send-event', 14: 'element-query'}
NONE = 2**64 - 1


def read_trace(path):
    raw = Path(path).read_bytes()
    if len(raw) < DATA_START:
        raise ValueError('Short ABI4 trace')
    magic, version, size, cap, reserved, npads, overflow, started, pid = HEADER.unpack_from(raw)
    if ((magic, version, size) != (b'MP2CTRL1', 4, 128) or
            not 16 <= cap <= 1048576 or len(raw) != DATA_START + 128 * cap or
            npads > 512 or not started or not pid):
        raise ValueError('ABI4 header contract')
    pads = {}
    for i in range(npads):
        slot = raw[64 + i * 512:64 + (i + 1) * 512]
        if b'\0' not in slot:
            raise ValueError('Truncated object dictionary')
        fields = slot.split(b'\0', 1)[0].decode('utf-8', errors='strict').split('\t', 2)
        if len(fields) != 3 or not all(fields):
            raise ValueError('Missing class/factory/path dictionary')
        pads[i + 1] = dict(type=fields[0], factory=fields[1], path=fields[2])
    rows = []
    incomplete = 0
    for i in range(min(cap, reserved)):
        values = RECORD.unpack_from(raw, DATA_START + i * 128)
        ts, pts, offset, duration, tid, pad, op, flow, flags = values[:9]
        aux, commit = values[9:17], values[17]
        if commit != i + 1:
            incomplete += 1
            continue
        if pad not in pads or op not in set(PAIRS) | set(PAIRS.values()) or tid == 0 or ts < started:
            raise ValueError('Malformed committed record')
        rows.append(dict(ts=ts, pts=pts, offset=offset, duration=duration,
                         tid=tid, pad=pad, op=op, flow=flow, flags=flags,
                         aux=aux, index=i))
    return dict(capacity=cap, reserved=reserved, pads=pads, overflow=overflow,
                incomplete=incomplete, started=started, pid=pid, records=rows,
                complete=not overflow and not incomplete and reserved <= cap)


def intervals(trace):
    stacks = collections.defaultdict(list)
    rows = []
    missing = collections.Counter()
    reverse = {v: k for k, v in PAIRS.items()}
    for record in trace['records']:
        key = (record['tid'], record['pad'])
        if record['op'] in PAIRS:
            stacks[key + (record['op'],)].append(record)
            continue
        op = reverse[record['op']]
        stack = stacks[key + (op,)]
        if not stack:
            missing[KINDS[op]] += 1
            continue
        before = stack.pop()
        if record['ts'] < before['ts']:
            raise ValueError('Call end precedes begin')
        rows.append(dict(begin=before['ts'], end=record['ts'],
                         elapsed_ns=record['ts'] - before['ts'],
                         tid=before['tid'], pad=before['pad'],
                         object=trace['pads'][before['pad']],
                         operation=KINDS[op], result=record['flow'],
                         pre_flow=before['flow'],
                         argument=before['flags'] if op in [6, 12] else before['flow'],
                         pts=before['pts'], offset=before['offset'],
                         duration=before['duration'], flags=before['flags'],
                         aux=before['aux']))
    return dict(rows=rows, unmatched_post=dict(missing),
                unmatched_pre={str(k): len(v) for k, v in stacks.items() if v})


def segment(row):
    if row['operation'] not in ['push-event', 'send-event'] or row['argument'] != 17934:
        raise ValueError('Not an observed SEGMENT event')
    aux = row['aux']
    rate = struct.unpack('<d', struct.pack('<Q', aux[4]))[0]
    applied = struct.unpack('<d', struct.pack('<Q', aux[5]))[0]
    if not math.isfinite(rate) or not math.isfinite(applied) or rate == 0 or applied == 0:
        raise ValueError('Invalid segment rates')
    return dict(format=row['pre_flow'],
                start=row['pts'], base=row['duration'], stop=aux[0],
                time=aux[1], position=aux[2], offset=aux[3], rate=rate,
                applied_rate=applied, segment_flags=aux[6], duration=aux[7],
                seqnum=row['offset'])


def summarize(trace):
    calls = intervals(trace)
    counts = collections.Counter(row['operation'] for row in calls['rows'])
    factories = collections.Counter(row['factory'] for row in trace['pads'].values())
    return dict(complete=trace['complete'], capacity=trace['capacity'],
                reserved=trace['reserved'], overflow=trace['overflow'],
                incomplete=trace['incomplete'], objects=len(trace['pads']),
                observed_factory_dictionary_entries=dict(factories),
                operations=dict(counts), unmatched_pre=calls['unmatched_pre'],
                unmatched_post=calls['unmatched_post'], record_bytes=128,
                source_of_factory_names='actual gst_element_get_factory',
                no_pixel_read=True, hardware_encoder_qualified=False)
