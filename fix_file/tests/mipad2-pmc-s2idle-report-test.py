#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import runpy
import unittest
from pathlib import Path


r = runpy.run_path(str(Path(__file__).with_name("mipad2-pmc-s2idle-report.py")))
CAPTURE = "a" * 32
OTHER = "b" * 32


def trace(capture=CAPTURE, masks=(0,), options=None):
    data = [
        (5, "tracing_mark_write", f"mipad2-pmc:{capture}:begin"),
        (17, "suspend_resume", "suspend_enter[1] begin"),
        (17, "suspend_resume", "suspend_enter[1] end"),
    ]
    for mask in masks:
        fields = dict.fromkeys(r["FIELDS"], 0)
        fields["forced_clks"] = mask
        data += [(17, "pmc_atom_s2idle", " ".join(f"{k}=0x{v:08x}" for k, v in fields.items())),
                 (17, "suspend_resume", "machine_suspend[1] begin"),
                 (17, "suspend_resume", "machine_suspend[1] end")]
    data += [
        (17, "suspend_resume", "console_resume_all[1] begin"),
        (17, "suspend_resume", "console_resume_all[1] end"),
        (5, "tracing_mark_write", f"mipad2-pmc:{capture}:end"),
    ]
    if options:
        options(data)
    return (f"# tracer: nop\n# entries-in-buffer/entries-written: {len(data)}/{len(data)}   #P:4\n" +
            "\n".join(f"    sample-worker-{pid}    [001] .....  {i}.000000: {name}: {v}"
                      for i, (pid, name, v) in enumerate(data, 1)))


def log(capture=CAPTURE, s0i3=3200000):
    s = [f"INFO PMC trace capture: {capture}",
         "INFO PMC sample window: 4000000us (per-counter limit 4500000us)"]
    for state in r["STATES"]:
        old, new = (r["PERIOD"] - 32, 32) if state == "S0IR" else (0, 0)
        if state == "S0I3":
            new = s0i3
        wrap = " (modulo counter period)" if new < old else ""
        delta = (new - old) % r["PERIOD"]
        s.append(f"INFO {state} delta:  {delta}us{wrap} (before {old}us, after {new}us)")
    s.append("INFO wake IRQ: 9; RTC fixed-event count: 1 -> 2")
    s.append("OK   S0I3 residency increased sufficiently" if s0i3 else
             "MISS S0I3 residency increased only 0us (minimum 2100000us)")
    return "\n".join(s)


class ReportTest(unittest.TestCase):
    def test_multiple_attempts_with_no_attribution(self):
        result = r["capture_report"](trace(masks=(1, 3)), log())
        self.assertEqual([x["forced_clks"] for x in result["attempts"]], [1, 3])
        self.assertEqual(result["residency_us"]["S0IR"], 64)
        self.assertTrue(result["s0i3_threshold_met"])
        self.assertIsNone(r["compare"]([result])["contrasted_bits"])

    def test_only_stable_exclusive_bits(self):
        good = r["capture_report"](trace(masks=(1, 3)), log())
        bad = r["capture_report"](trace(OTHER, (4, 6)), log(OTHER, 0))
        self.assertEqual(r["compare"]([good, bad])["contrasted_bits"]["forced_clks"], {
            "set_in_all_misses_and_no_met": 4, "set_in_all_met_and_no_misses": 1,
        })
        self.assertFalse(bad["s0i3_threshold_met"])
        with self.assertRaisesRegex(ValueError, "duplicate capture"):
            r["compare"]([good, good])

    def test_wrong_capture_and_overwrite(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            r["capture_report"](trace(OTHER), log())
        with self.assertRaisesRegex(ValueError, "lost entries"):
            r["capture_report"](trace().replace("9/9", "9/10"), log())

    def test_no_second_cycle_or_missing_snapshot(self):
        with self.assertRaisesRegex(ValueError, "unexpected power"):
            r["capture_report"](trace(options=lambda d: d.insert(-1, d[1])), log())
        with self.assertRaisesRegex(ValueError, "unexpected power"):
            r["capture_report"](trace(options=lambda d: d.pop(3)), log())

    def test_bad_clock_bitmap_or_drifted_task(self):
        with self.assertRaisesRegex(ValueError, "clock bits"):
            r["capture_report"](trace(masks=(64,)), log())
        with self.assertRaisesRegex(ValueError, "unpaired"):
            r["capture_report"](trace().replace("worker-17    [001] .....  4.", "worker-18    [001] .....  4."),
                                log())

    def test_forged_residency_or_wrong_wake(self):
        with self.assertRaisesRegex(ValueError, "invalid S0I3"):
            r["capture_report"](trace(), log().replace("after 3200000us", "after 6400000us"))
        with self.assertRaisesRegex(ValueError, "missing RTC wake"):
            r["capture_report"](trace(), log().replace("1 -> 2", "1 -> 3"))
        with self.assertRaisesRegex(ValueError, "inconsistent missed"):
            r["capture_report"](trace(), log(s0i3=0).replace("increased only 0us", "increased only 32us"))
        with self.assertRaisesRegex(ValueError, "expected exactly one S0i3 result"):
            r["capture_report"](trace(), log().replace("OK   S0I3 residency increased sufficiently", "MISS no wake source"))


if __name__ == "__main__":
    unittest.main()
