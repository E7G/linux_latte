# SPDX-License-Identifier: GPL-2.0
"""Strict function-entry/return metadata decoder. No address/argument parsing."""
from collections import Counter, defaultdict
import re
import statistics

ROLES = ('qbuf', 'irq', 'css_queue')
HEADER = re.compile(r'\s(\d+)\.(\d{1,9}):\s+(?:[A-Za-z0-9_]+:)?([A-Za-z0-9_]+):')
TASK = re.compile(r'-(\d+)\s+\[(\d+)\]')


def common(line):
    match = HEADER.search(line)
    if not match:
        raise ValueError('Unrecognized event timestamp/header')
    task = TASK.search(line[:match.start()])
    if not task:
        raise ValueError('Missing task/CPU event header')
    return dict(ts=int(match[1])*10**9+int(match[2].ljust(9, '0')),
                pid=int(task[1]), cpu=int(task[2]), event=match[3],
                resolution_ns=10**(9-len(match[2])))


def parse(text, prefix):
    owned = re.compile(re.escape(prefix)+r'_(qbuf|irq|css_queue)_(begin|end)$')
    records = []
    for index, line in enumerate(text.splitlines()):
        if prefix+'_' not in line:
            continue
        header = common(line)
        event = owned.fullmatch(header['event'])
        if not event:
            raise ValueError('Unknown owned probe event')
        if header['pid'] <= 0:
            raise ValueError('Function probes require a task')
        records.append(dict(header, role=event[1], kind=event[2], line=index))
    if not records:
        raise ValueError('No owned function probe records')
    return records


def pair(records, profile=None):
    stacks = defaultdict(list)
    last = {}
    calls = []
    counts = Counter()
    for row in records:
        if row['pid'] in last and row['ts'] < last[row['pid']]:
            raise ValueError('Nonmonotonic per-task trace clock')
        last[row['pid']] = row['ts']
        counts[row['event']] += 1
        key = (row['pid'], row['role'])
        if row['kind'] == 'begin':
            stacks[key].append(row)
        elif row['kind'] == 'end':
            if not stacks[key]:
                raise ValueError('Return without matching entry')
            before = stacks[key].pop()
            calls.append(dict(role=row['role'], pid=row['pid'], begin=before['ts'],
                              end=row['ts'], elapsed_ns=row['ts']-before['ts'],
                              begin_line=before['line'], end_line=row['line']))
        else:
            raise ValueError('Invalid probe record kind')
    if any(stacks.values()):
        raise ValueError('Function entry without matching return')
    if set(c['role'] for c in calls) != set(ROLES):
        raise ValueError('Missing selected function role')
    if profile is not None:
        if set(counts) != set(profile):
            raise ValueError('Trace/profile event population mismatch')
        if any(v['missed'] != 0 or counts[n] != v['hits'] for n,v in profile.items()):
            raise ValueError('Probe miss or trace/profile count mismatch')
    return calls


def stats(values):
    if not values:
        raise ValueError('Empty timing population')
    values = sorted(values)
    return dict(count=len(values), min_ns=values[0], median_ns=statistics.median(values),
                p95_ns=values[(len(values)-1)*95//100],
                p99_ns=values[(len(values)-1)*99//100], max_ns=values[-1],
                above1ms=sum(v>10**6 for v in values), above10ms=sum(v>10**7 for v in values))


def summarize(records, calls):
    return dict(function_elapsed_wall_time={role:stats([c['elapsed_ns'] for c in calls if c['role']==role]) for role in ROLES},
                unique_tasks_per_role={role:len({c['pid'] for c in calls if c['role']==role}) for role in ROLES},
                text_timestamp_resolution_ns=max(r['resolution_ns'] for r in records),
                all_entry_return_pairs_complete=True, cache_flush_instruction_time_isolated=False,
                exclusive_CPU_time_claimed=False, raw_rows_exported=False)
