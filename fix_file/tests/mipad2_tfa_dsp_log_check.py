#!/usr/bin/env python3
"""Validate both TFA DSP initializations from one explicitly marked live run.

Old successes, a single working amp, or a missing/wrapped marker never pass.
This checks initialization logs only, not acoustic output or live clock state.
"""
import argparse
from pathlib import Path
import re

DEVICES = ("i2c-tfa9890:00", "i2c-tfa9890:01")


def scoped_lines(text, marker):
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if marker in line]
    if len(matches) != 1:
        raise ValueError("run marker missing or duplicated; cannot scope evidence")
    return lines[matches[0] + 1:]


def check(text, marker, containers_only=False):
    lines = scoped_lines(text, marker)
    ready, results = set(), {}
    for line in lines:
        for dev in DEVICES:
            if f"tfa98xx {dev}:" not in line:
                continue
            if "factory container ready:" in line and "defer_dsp_start=0" in line:
                ready.add(dev)
            match = re.search(r"factory DSP init ret=(-?\d+)\b", line)
            if match:
                results[dev] = int(match[1])
    missing = set(DEVICES) - ready
    if missing:
        raise ValueError(f"current-run container evidence missing: {sorted(missing)}")
    if not containers_only:
        for dev in DEVICES:
            if results.get(dev) != 0:
                raise ValueError(f"{dev}: latest current-run DSP init={results.get(dev)!r}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("marker")
    parser.add_argument("--containers-only", action="store_true")
    args = parser.parse_args()
    try:
        results = check(args.log.read_text(), args.marker, args.containers_only)
    except ValueError as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS current-run {'containers' if args.containers_only else 'DSP init'}: {results}")


if __name__ == "__main__":
    main()
