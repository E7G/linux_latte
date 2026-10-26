"""Strict metadata boundary joins. No temporal nearest-neighbour matching."""
from collections import Counter

NONE = 2**64 - 1


def segment_event_success(row):
    # gstpad.c: send-event-post receives GstFlowReturn (OK=0), while
    # push-event-post receives gboolean (TRUE=1). They are not interchangeable.
    return row['argument'] == 17934 and (
        (row['operation'] == 'send-event' and row['result'] == 0) or
        (row['operation'] == 'push-event' and row['result'] == 1))


def unique_index(rows, key):
    result = {}
    for row in rows:
        k = key(row)
        if k in result:
            raise ValueError('Ambiguous boundary identity')
        result[k] = row
    return result


def exact_subset(left, right, left_key, right_key):
    """Every left identity must exist exactly once; report explicit right surplus."""
    li = unique_index(left, left_key)
    ri = unique_index(right, right_key)
    if any(k not in ri for k in li):
        raise ValueError('Missing exact boundary identity')
    pairs = [(r, ri[left_key(r)]) for r in left]
    if [left_key(a) for a, _ in pairs] != [right_key(r) for r in right if right_key(r) in li]:
        raise ValueError('Boundary order mismatch')
    return pairs, len(ri) - len(li)


def running_time_rate_one(pts, segment):
    """Restricted GstSegment to_running_time_full, verified against 1.28.7.

    Keep unsupported rates/formats explicit rather than fit a timestamp offset.
    gst_segment.c: start + offset; signed(position - start) + base.
    applied_rate/time do not enter to_running_time_full's forward calculation.
    """
    if segment['format'] != 3 or segment['rate'] != 1.0 or segment['applied_rate'] != 1.0:
        raise ValueError('Unsupported observed segment')
    if any(not isinstance(segment[k], int) or not 0 <= segment[k] < NONE
           for k in ('start', 'offset', 'base')) or not isinstance(pts, int) or not 0 <= pts < NONE:
        raise ValueError('Invalid timestamp or segment integer')
    start = segment['start'] + segment['offset']
    if start >= NONE:
        raise ValueError('Segment integer overflow')
    return pts - start + segment['base']


def quantize_ns(ns, numerator, denominator):
    """GStreamer scale_round to a positive rational stream time_base."""
    if any(not isinstance(x, int) for x in (ns, numerator, denominator)) or ns < 0 or numerator <= 0 or denominator <= 0:
        raise ValueError('Unsupported timebase/timestamp')
    divisor = 10**9 * numerator
    return (ns * denominator + divisor // 2) // divisor


def require_ordered_bijection(left, right, left_key, right_key):
    pairs, surplus = exact_subset(left, right, left_key, right_key)
    if surplus:
        raise ValueError('Unexpected extra downstream identity')
    return pairs


def gap_summary(values):
    gaps = [b-a for a, b in zip(values, values[1:])]
    return dict(frames=len(values), gaps_above50ms=sum(g > 50_000_000 for g in gaps),
                nonpositive_gaps=sum(g <= 0 for g in gaps), max_gap_ns=max(gaps, default=None))
