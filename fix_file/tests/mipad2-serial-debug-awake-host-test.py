#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the serial debug guard without systemd, logind, or a real sleep."""

import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "awake", Path(__file__).with_name("mipad2-serial-debug-awake.py")
)
awake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(awake)

OWN = ["sleep:idle", awake.WHO, awake.WHY, "block", 0, 42]


class Fake:
    def __init__(self, *snapshots):
        self.snapshots = iter(snapshots)
        self.calls = []
        self.delays = []
        self.guard = awake.Guard(self.command, self.delays.append)

    def command(self, argv):
        self.calls.append(argv)
        if argv[:2] == ["systemctl", "show"]:
            unit, self.inhibitors = next(self.snapshots)
            return "\n".join(f"{k}={v}" for k, v in unit.items())
        if argv[0] == "busctl":
            return json.dumps({"type": "a(ssssuu)", "data": [self.inhibitors]})
        return ""

    def changes(self):
        return [c for c in self.calls if c[0] == "systemd-run" or c[:2] == ["systemctl", "stop"]]


def loaded(rows, **changes):
    unit = dict(LoadState="loaded", ActiveState="active", Transient="yes", MainPID="42",
                ActiveEnterTimestamp="now", RuntimeMaxUSec="2h")
    return dict(unit, **changes), rows


def absent():
    return loaded([], LoadState="not-found", ActiveState="inactive", Transient="no", MainPID="0")


class TestGuard(unittest.TestCase):
    def test_status_requires_only_reads_and_accepts_another_unrelated_lock(self):
        fake = Fake(loaded([["sleep", "Desktop", "do not idle", "block", 0, 99], OWN]))
        self.assertEqual(fake.guard.check()["MainPID"], "42")
        self.assertEqual(fake.changes(), [])

    def test_status_fails_for_absent_unit(self):
        fake = Fake(absent())
        with self.assertRaisesRegex(ValueError, "not verified"):
            fake.guard.check()
        self.assertEqual(fake.changes(), [])

    def test_same_name_is_not_enough(self):
        for field, bad_value in enumerate(("sleep", "other", "other", "block-weak", 1000, 43)):
            with self.subTest(field=field):
                row = OWN.copy()
                row[field] = bad_value
                fake = Fake(loaded([row]))
                with self.assertRaisesRegex(ValueError, "not verified"):
                    fake.guard.stop()
                self.assertEqual(fake.changes(), [])

    def test_non_transient_failed_or_unbounded_service_not_owned(self):
        for properties in ({"Transient": "no"}, {"ActiveState": "failed"},
                           {"RuntimeMaxUSec": "infinity"}, {"MainPID": "0"}):
            with self.subTest(properties=properties):
                fake = Fake(loaded([OWN], **properties))
                with self.assertRaisesRegex(ValueError, "already exists"):
                    fake.guard.start(5)
                self.assertEqual(fake.changes(), [])

    def test_start_is_detached_bounded_and_waits_for_logind(self):
        fake = Fake(absent(), loaded([]), loaded([OWN]))
        unit, started = fake.guard.start(30)
        self.assertTrue(started)
        self.assertEqual(unit["MainPID"], "42")
        self.assertEqual(fake.delays, [0.2])
        self.assertEqual(fake.changes(), [[
            "systemd-run", f"--unit={awake.UNIT}", "--collect", "--service-type=exec",
            "--property=After=systemd-logind.service",
            "--property=Wants=systemd-logind.service", "--property=RuntimeMaxSec=1805s",
            "/usr/bin/systemd-inhibit", "--what=sleep:idle", "--mode=block",
            f"--who={awake.WHO}", f"--why={awake.WHY}", "/usr/bin/sleep", "1800",
        ]])

    def test_start_does_not_restart_the_active_lock(self):
        fake = Fake(loaded([OWN]))
        _, started = fake.guard.start(30)
        self.assertFalse(started)
        self.assertEqual(fake.changes(), [])

    def test_startup_without_inhibitor_never_reports_success(self):
        fake = Fake(absent(), *(loaded([]) for _ in range(10)))
        with self.assertRaisesRegex(ValueError, "logind did not confirm"):
            fake.guard.start(1)
        self.assertEqual(len(fake.changes()), 1)
        self.assertEqual(fake.delays, [0.2] * 10)

    def test_stop_only_verified_transient_unit(self):
        fake = Fake(loaded([OWN]))
        fake.guard.stop()
        self.assertEqual(fake.changes(), [["systemctl", "stop", awake.UNIT]])

    def test_invalid_bus_reply_fails_closed(self):
        fake = Fake(loaded(None))
        with self.assertRaisesRegex(ValueError, "unexpected logind inhibitor response"):
            fake.guard.stop()
        self.assertEqual(fake.changes(), [])

    def test_duration_boundaries(self):
        self.assertEqual(awake.timeout_minutes("1"), 1)
        self.assertEqual(awake.timeout_minutes("120"), 120)
        for token in ("0", "121", "-1", "1h"):
            with self.subTest(token=token), self.assertRaises((ValueError, awake.argparse.ArgumentTypeError)):
                awake.timeout_minutes(token)


if __name__ == "__main__":
    unittest.main()
