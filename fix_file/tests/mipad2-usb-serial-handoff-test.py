#!/usr/bin/env python3
"""Test the actual serial handoff guard on fake files, never USB hardware."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'packages/mipad2-usb-serial/mipad2-usb-serial'

class SerialHandoff(unittest.TestCase):
    def setUp(self):
        self.source = HELPER.read_text()
        match = re.search(r'(?ms)^serial_gadget_is_bound\(\) \{\n.*?^\}', self.source)
        self.assertIsNotNone(match)
        self.guard = match.group(0)
        self.temp = tempfile.TemporaryDirectory(prefix='mipad2-serial-handoff-')
        self.addCleanup(self.temp.cleanup)
        self.gadget = Path(self.temp.name) / 'gadget'
        (self.gadget / 'functions/acm.usb0').mkdir(parents=True)
        (self.gadget / 'configs/c.1').mkdir(parents=True)
        (self.gadget / 'UDC').write_text('dwc3.0.auto\n')
        (self.gadget / 'idVendor').write_text('0x1d6b\n')
        (self.gadget / 'idProduct').write_text('0x0104\n')
        (self.gadget / 'configs/c.1/acm.usb0').symlink_to(self.gadget / 'functions/acm.usb0')

    def check(self, expected):
        before = {str(p): p.read_bytes() for p in self.gadget.rglob('*') if p.is_file() and not p.is_symlink()}
        p = subprocess.run(['sh', '-c', 'set -eu\n' + self.guard + '\nserial_gadget_is_bound "$1" "$2"',
                            'test', str(self.gadget), 'dwc3.0.auto'], capture_output=True, text=True)
        self.assertEqual(p.returncode, expected, p.stderr)
        after = {str(p): p.read_bytes() for p in self.gadget.rglob('*') if p.is_file() and not p.is_symlink()}
        self.assertEqual(before, after)

    def test_owned_serial_preserved(self):
        self.check(0)

    def test_no_host_does_not_force_rebind(self):
        (self.gadget / 'state').write_text('not attached\n')
        self.check(0)

    def test_unbound_is_not_preserved(self):
        (self.gadget / 'UDC').write_text('\n')
        self.check(1)

    def test_wrong_udc_is_not_preserved(self):
        (self.gadget / 'UDC').write_text('other-controller\n')
        self.check(1)

    def test_wrong_ids_are_not_preserved(self):
        for name in ('idVendor', 'idProduct'):
            path = self.gadget / name
            original = path.read_text()
            path.write_text('0xffff\n')
            self.check(1)
            path.write_text(original)

    def test_missing_function_is_not_preserved(self):
        (self.gadget / 'functions/acm.usb0').rmdir()
        self.check(1)

    def test_wrong_link_is_not_preserved(self):
        link = self.gadget / 'configs/c.1/acm.usb0'
        link.unlink()
        (self.gadget / 'functions/rndis.usb0').mkdir()
        link.symlink_to(self.gadget / 'functions/rndis.usb0')
        self.check(1)

    def test_guard_precedes_disconnect(self):
        call = self.source.index('if serial_gadget_is_bound "$G" "$UDC"; then')
        self.assertLess(call, self.source.index('> /sys/bus/gadget/drivers/g_ether/unbind'))
        self.assertLess(call, self.source.index('[ -f "$G/UDC" ] && printf'))

if __name__ == '__main__':
    unittest.main()
