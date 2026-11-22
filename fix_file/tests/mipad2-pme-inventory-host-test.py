#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise the actual read-only PME inventory on fake sysfs/proc trees."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).with_name("mipad2-pme-inventory.py")
SPEC = importlib.util.spec_from_file_location("mipad2_pme_inventory", FILE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class Inventory(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.device("INT0002:02", r"\_SB_.GPED", "1", "0", "INT0002 Virtual GPIO")
        self.device("INT33FF:13", r"\_SB_.GPO4", "5", "15")
        self.irq(9, "9", "acpi,INT0002", "IO-APIC", "disabled")
        self.irq(108, "108", "", "IO-APIC", "disabled")
        self.irq(141, "2", "ACPI:Event", "INT0002 Virtual GPIO", "enabled")
        self.rows([" 141: 441 5 INT0002 Virtual GPIO 2 ACPI:Event"])

    def put(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value + "\n")

    def device(self, name, acpi, uid, status, driver=None):
        for k, value in {"path": acpi, "uid": uid, "status": status}.items():
            self.put(f"sys/bus/acpi/devices/{name}/{k}", value)
        path = self.root / "sys/bus/platform/devices" / name
        path.mkdir(parents=True, exist_ok=True)
        if driver:
            target = self.root / "sys/bus/platform/drivers" / driver
            target.mkdir(parents=True, exist_ok=True)
            (path / "driver").symlink_to(target, target_is_directory=True)

    def irq(self, n, hwirq, actions, chip, wakeup):
        for k, value in {"hwirq": hwirq, "actions": actions,
                         "chip_name": chip, "wakeup": wakeup}.items():
            self.put(f"sys/kernel/irq/{n}/{k}", value)

    def rows(self, rows, cpus="  CPU0 CPU3"):
        self.put("proc/interrupts", "\n".join([cpus, *rows]))

    def result(self):
        report = AUDIT.board_inventory(self.root)
        self.assertIs(report["wake_delivery_tested"], False)
        return report

    def test_raw_sta_zero_does_not_hide_bound_sci(self):
        r = self.result()
        self.assertEqual(r["result"], "gped-sci-registered")
        self.assertEqual(r["gped"]["raw_sta"], "0")
        self.assertEqual(r["gped"]["name"], "INT0002:02")
        self.assertEqual(r["gped_pin2_event"], {
            "counts": {"CPU0": 441, "CPU3": 5}, "irq": 141, "wake_enabled": True})

    def test_firmware_status_alone_does_not_assert_registration(self):
        (self.root / "sys/bus/platform/devices/INT0002:02/driver").unlink()
        self.put("sys/bus/acpi/devices/INT0002:02/status", "15")
        self.assertEqual(self.result()["result"], "no-verified-provider")

    def test_reject_missing_sci_action(self):
        self.irq(9, "9", "acpi", "IO-APIC", "disabled")
        self.assertEqual(self.result()["result"], "no-verified-provider")

    def test_reject_duplicate_or_bad_irq_rows(self):
        for cpus, rows in [
            ("CPU0 CPU0", ["141: 1 2 INT0002 Virtual GPIO 2 ACPI:Event"]),
            ("CPU0 CPU3", ["141: 1 INT0002 Virtual GPIO 2 ACPI:Event"]),
            ("CPU0 CPU3", ["141: 1 2 INT0002 Virtual GPIO 2 ACPI:Event"] * 2),
            ("CPU0 CPU3", ["141: 1 2 chv-gpio 6 ACPI:Event"]),
        ]:
            with self.subTest(cpus=cpus, rows=rows):
                self.rows(rows, cpus)
                self.assertIsNone(self.result()["gped_pin2_event"])
                self.assertEqual(self.result()["result"], "no-verified-provider")

    def test_child_must_match_live_sysfs(self):
        self.irq(141, "6", "ACPI:Event", "chv-gpio", "enabled")
        self.assertIsNone(self.result()["gped_pin2_event"])

    def test_broken_gpo4_driver_link_is_not_definitively_unbound(self):
        p = self.root / "sys/bus/platform/devices/INT33FF:13/driver"
        p.symlink_to(p.parent / "missing", target_is_directory=True)
        report = self.result()
        self.assertEqual(report["gpo4"]["driver_state"], "unknown")
        self.assertEqual(report["result"], "no-verified-provider")

    def test_gpo4_binding_is_not_wake_delivery_proof(self):
        self.device("INT33FF:13", r"\_SB_.GPO4", "5", "15", "cherryview-pinctrl")
        self.assertEqual(self.result()["result"], "both-controllers-bound")
        (self.root / "sys/bus/platform/devices/INT0002:02/driver").unlink()
        self.assertEqual(self.result()["result"], "gpo4-bound-unverified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
