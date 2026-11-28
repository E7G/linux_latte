#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run the production touchscreen predicate against fake input sysfs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_name("mipad2-hardware-smoke.sh").read_text()
CHECK = SOURCE.split("# BEGIN MIPAD2_TOUCHSCREEN_CHECK\n", 1)[1].split(
    "# END MIPAD2_TOUCHSCREEN_CHECK", 1)[0]
TOUCH = {"properties": "2", "capabilities/key": "400 0 0 0 0 0",
         "capabilities/abs": "3273800000000003"}
PEN = {"properties": "0", "capabilities/key": "c03 0 0 0 0 0",
       "capabilities/abs": "1000003"}
KEYBOARD = {"properties": "0", "capabilities/key": "40000800 2000000000000000 0",
            "capabilities/abs": "0"}


class Touchscreen(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory(prefix="mipad2 touch ")
        self.addCleanup(root.cleanup)
        self.sys = Path(root.name)
        (self.sys / "class/input").mkdir(parents=True)
        self.driver = self.sys / "bus/hid/drivers/hid-multitouch"
        self.driver.mkdir(parents=True)

    def event(self, n, caps, client="i2c-FTSC1000", hid="0018:2808:509C.0002",
              phys=None, driver=True, **ids):
        parent = self.sys / "devices/platform/INTCFD9:00/i2c-4" / client / hid
        if driver:
            link = parent / "driver"
            if not link.is_symlink():
                parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(self.driver, target_is_directory=True)
        device = parent / "input" / f"input{n + 1}"
        event = self.sys / "class/input" / f"event{n}"
        event.mkdir()
        event.joinpath("device").symlink_to(device, target_is_directory=True)
        for path, value in {
            "phys": phys or client, "id/bustype": "0018", "id/vendor": "2808",
            "id/product": "509c", **caps,
            **{f"id/{k}": v for k, v in ids.items()},
        }.items():
            target = device / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value + "\n")

    def probe(self, expected=None):
        p = subprocess.run(["sh", "-euc", CHECK + '\nmipad2_touchscreen_node "$1"',
                            "test", str(self.sys)], text=True, capture_output=True, timeout=5)
        if expected is not None:
            self.assertEqual(p.returncode, 0, p)
            self.assertEqual(p.stdout.strip(), expected)
        else:
            self.assertEqual(p.returncode, 1, p)
            self.assertEqual(p.stdout, "", p)

    def test_real_board_children_only_select_touch(self):
        self.event(8, PEN)
        self.event(9, KEYBOARD)
        self.event(23, TOUCH)
        self.probe("event23")

    def test_acpi_named_client_also_works(self):
        self.event(42, TOUCH, client="i2c-FTSC1000:00")
        self.probe("event42")

    def test_pen_and_keyboard_are_not_touchscreen(self):
        self.event(8, PEN)
        self.event(9, KEYBOARD)
        self.probe()

    def test_other_i2c_client_and_usb_device_do_not_count(self):
        self.event(12, TOUCH, client="i2c-FTSC2000", phys="i2c-FTSC1000")
        self.event(20, TOUCH, hid="0003:2808:509C.0003", bustype="0003")
        self.probe()

    def test_requires_driver_identity_and_expected_product(self):
        self.event(6, TOUCH, driver=False, hid="0018:2808:509C.0001")
        self.event(21, TOUCH, product="f00d")
        self.event(25, TOUCH, phys="unknown")
        self.probe()

    def test_missing_or_malformed_multitouch_capabilities_do_not_count(self):
        self.event(6, dict(TOUCH, **{"capabilities/abs": "1000003"}))
        self.event(7, dict(TOUCH, **{"capabilities/abs": "3233800000000003"}))
        self.event(8, dict(TOUCH, **{"capabilities/key": "400 0 0 0 0"}))
        self.event(9, dict(TOUCH, **{"properties": "2\nmalformed"}))
        self.event(10, dict(TOUCH, **{"capabilities/abs": "3273800000000003 bad!"}))
        self.probe()

    def test_duplicate_qualifying_devices_fail(self):
        self.event(6, TOUCH)
        self.event(7, TOUCH)
        self.probe()


if __name__ == "__main__":
    unittest.main(verbosity=2)
