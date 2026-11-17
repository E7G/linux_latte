#!/usr/bin/env python3
"""Reviewed 7.2.15 source-resolution identities, not hardware qualification."""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import tempfile
import unittest

PINS = {
    'arch/x86/Kconfig.cpu': '1fd45d32d7a06b6489e7eb7693be23a65bcbdcd2a20944b59c48d51c3c27736f',
    'drivers/ata/ahci.c': '2bb21b9b10cf22a46ad227af92eb7253d511f989c96d3df64273e0a42125f6f5',
}


def verify(root):
    makefile = (root / 'Makefile').read_text()
    for key, value in [('VERSION', '7'), ('PATCHLEVEL', '2'), ('SUBLEVEL', '15')]:
        if re.findall(r'^' + key + r'\s*=\s*(\S+)\s*$', makefile, re.M) != [value]:
            raise ValueError('Unexpected source version: ' + key)
    for path, expected in PINS.items():
        data = (root / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Unreviewed conflict resolution: ' + path)
    cpu = (root / 'arch/x86/Kconfig.cpu').read_text()
    ahci = (root / 'drivers/ata/ahci.c').read_text()
    if (cpu.count('config MSILVERMONT\n') != 1 or
            cpu.count('config RUSTC_HAS_APXF\n') != 1 or
            'depends on !RUST || RUSTC_HAS_APXF' not in cpu):
        raise ValueError('Missing CPU optimization or upstream APX gate')
    if ('static irqreturn_t ahci_mv_irq_handler' not in ahci or
            'static int ahci_remap_check' not in ahci or
            'rc = ahci_remap_check(pdev, ahci_pci_bar, hpriv);' not in ahci):
        raise ValueError('Lost AHCI interrupt fix or existing NVMe handoff')


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mipad2-stable-gates-')
        self.assertEqual(Path(self.tmp.name).resolve().parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(Path(self.tmp.name).name.startswith('mipad2-stable-gates-'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ['Makefile', *PINS]:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, dest)

    def change(self, path, before, after):
        file = self.root / path
        data = file.read_bytes()
        self.assertIn(before, data)
        file.write_bytes(data.replace(before, after, 1))

    def test_reviewed_source_passes(self):
        verify(self.root)

    def test_wrong_patchlevel_rejected(self):
        self.change('Makefile', b'SUBLEVEL = 15\n', b'SUBLEVEL = 14\n')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_silvermont_rejected(self):
        self.change('arch/x86/Kconfig.cpu', b'config MSILVERMONT\n', b'config MOTHER\n')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_apx_gate_rejected(self):
        self.change('arch/x86/Kconfig.cpu', b'depends on !RUST || RUSTC_HAS_APXF', b'depends on !RUST')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_interrupt_fix_rejected(self):
        self.change('drivers/ata/ahci.c', b'static irqreturn_t ahci_mv_irq_handler', b'static irqreturn_t ahci_other_handler')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_lost_remap_return_type_rejected(self):
        self.change('drivers/ata/ahci.c', b'static int ahci_remap_check', b'static void ahci_remap_check')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_unreviewed_byte_change_rejected(self):
        file = self.root / 'arch/x86/Kconfig.cpu'
        file.write_bytes(file.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_file_rejected(self):
        (self.root / 'drivers/ata/ahci.c').unlink()
        with self.assertRaises(FileNotFoundError):
            verify(self.root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[3])
    options = parser.parse_args()
    SOURCE = options.source.resolve()
    unittest.main(argv=[__file__])
