#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare explicitly paired Mi Pad 2 PMC trace and residency logs offline."""

import argparse
import json
import re
from functools import reduce
from operator import and_, or_
from pathlib import Path

ID = r"[0-9a-f]{32}"
FIELDS = ("func_dis", "func_dis_2", "d3_sts_0", "d3_sts_1", "pss", "forced_clks")
STATES = ("S0IR", "S0I1", "S0I2", "S0I3", "S0")
PERIOD = (1 << 32) * 32
MARK = re.compile(rf"mipad2-pmc:({ID}):(begin|end)")
RECORD = re.compile(
    r"^\s*.*?-(\d+)\s+\[\d+\].*?\s+\d+\.\d+: "
    r"(tracing_mark_write|suspend_resume|pmc_atom_s2idle): (.*)$"
)
POWER = re.compile(r"(suspend_enter|machine_suspend|console_resume_all)\[(\d+)\] (begin|end)")
REGS = re.compile(" ".join(rf"{f}=0x([0-9a-f]{{8}})" for f in FIELDS))


def one(pattern, text, label):
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {label}")
    return matches[0]


def trace_samples(trace, capture):
    buffered, written = map(int, one(
        r"^#\s+entries-in-buffer/entries-written:\s*(\d+)/(\d+)\s",
        trace, "trace buffer header",
    ))
    if buffered != written:
        raise ValueError("trace buffer lost entries")
    mark = None
    power = "start"
    owner = None
    rows = []
    sequence = {
        ("start", "suspend_enter", "begin"): "preparing",
        ("preparing", "suspend_enter", "end"): "ready",
        ("sample", "machine_suspend", "begin"): "entering",
        ("entering", "machine_suspend", "end"): "ready",
        ("ready", "console_resume_all", "begin"): "resuming",
        ("resuming", "console_resume_all", "end"): "resumed",
    }
    for line in trace.splitlines():
        match = RECORD.fullmatch(line)
        if not match:
            continue
        pid, event, data = match.groups()
        if event == "tracing_mark_write":
            if not data.startswith("mipad2-pmc:"):
                continue
            m = MARK.fullmatch(data)
            if not m or m[1] != capture:
                raise ValueError("trace marker does not match residency log")
            if m[2] == "begin" and mark is None:
                mark = "open"
            elif m[2] == "end" and mark == "open" and power == "resumed":
                mark = "closed"
            else:
                raise ValueError("duplicate or out-of-order trace marker")
            continue
        if event == "suspend_resume":
            m = POWER.fullmatch(data)
            if not m:
                continue
            action, state, edge = m.groups()
            if mark != "open" or state != "1":
                raise ValueError("power transition not in the marked s2idle cycle")
            if power == "start":
                owner = pid
            step = (power, action, edge)
            if owner != pid or step not in sequence:
                raise ValueError(f"unexpected power transition or task: {data}")
            power = sequence[step]
        else:
            regs = REGS.fullmatch(data)
            if mark != "open" or power != "ready" or owner != pid or not regs:
                raise ValueError("unpaired or malformed PMC snapshot")
            row = dict(zip(FIELDS, (int(x, 16) for x in regs.groups())))
            if row["forced_clks"] & ~0x3f:
                raise ValueError("unexpected PMC clock bits")
            rows.append(row)
            power = "sample"
    if mark != "closed" or not rows:
        raise ValueError("no complete marked cycle with PMC samples")
    return rows


def residency(log):
    capture = one(rf"^INFO PMC trace capture: ({ID})$", log, "capture ID")
    elapsed, limit = map(int, one(
        r"^INFO PMC sample window: (\d+)us \(per-counter limit (\d+)us\)$",
        log, "bounded PMC sample window",
    ))
    if limit != elapsed + elapsed // 10 + 100000 or limit >= PERIOD:
        raise ValueError("invalid PMC sample window")
    counters = {}
    for name in STATES:
        delta, wrapped, before, after = one(
            rf"^INFO {name} delta: +(\d+)us( \(modulo counter period\))?"
            r" \(before (\d+)us, after (\d+)us\)$", log, f"{name} delta",
        )
        delta, before, after = map(int, (delta, before, after))
        if (before >= PERIOD or after >= PERIOD or before % 32 or after % 32 or
                delta != (after - before) % PERIOD or delta > limit or
                bool(wrapped) != (after < before)):
            raise ValueError(f"invalid {name} counter sample")
        counters[name] = delta
    irq, before, after = map(int, one(
        r"^INFO wake IRQ: (\d+); RTC fixed-event count: (\d+) -> (\d+)$",
        log, "RTC wake evidence",
    ))
    if irq != 9 or after - before != 1:
        raise ValueError("missing RTC wake evidence")
    status = one(r"^(OK +S0I3 residency increased sufficiently|"
                 r"MISS S0I3 residency increased only \d+us \(minimum \d+us\))$",
                 log, "S0i3 result after RTC checks")
    if status.startswith("MISS"):
        value, minimum = map(int, re.findall(r"(\d+)us", status))
        if value != counters["S0I3"] or not value < minimum:
            raise ValueError("inconsistent missed S0i3 result")
    return capture, counters, status.startswith("OK")


def capture_report(trace, log):
    capture, counters, met = residency(log)
    return dict(id=capture, residency_us=counters, s0i3_threshold_met=met,
                attempts=trace_samples(trace, capture))


def compare(runs):
    if len({r["id"] for r in runs}) != len(runs):
        raise ValueError("duplicate capture ID")
    met, missed = (
        [a for r in runs if r["s0i3_threshold_met"] == flag for a in r["attempts"]]
        for flag in (True, False)
    )
    contrasts = None
    if met and missed:
        contrasts = {
            field: {
                "set_in_all_misses_and_no_met": reduce(and_, (x[field] for x in missed))
                & ~reduce(or_, (x[field] for x in met)),
                "set_in_all_met_and_no_misses": reduce(and_, (x[field] for x in met))
                & ~reduce(or_, (x[field] for x in missed)),
            } for field in FIELDS
        }
    return dict(captures=runs, contrasted_bits=contrasts, interpretation=(
        "Descriptive bit differences, not causes or per-attempt residency. "
        "If there is only one class of captures, no contrast is reported."
    ))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", nargs=2, action="append", required=True,
                    type=Path, metavar=("TRACE", "RTC_LOG"))
    args = ap.parse_args()
    try:
        runs = [capture_report(trace.read_text(), log.read_text()) for trace, log in args.run]
        report = compare(runs)
    except (OSError, ValueError) as exc:
        ap.exit(1, f"{ap.prog}: {exc}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
