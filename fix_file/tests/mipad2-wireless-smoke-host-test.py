#!/usr/bin/env python3
"""Exercise the actual POSIX smoke checks with an isolated fake sysfs tree."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

source = Path(__file__).with_name("mipad2-hardware-smoke.sh").read_text()
checks = source.split("# BEGIN MIPAD2_WIRELESS_CHECKS\n", 1)[1].split(
    "# END MIPAD2_WIRELESS_CHECKS", 1)[0]
release = "7.2.15-mipad2-integrated-lpat13"
wifi_bin = "brcmfmac4356-pcie.bin"
nvram = "brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt"
bt_patch = "BCM4356A2.hcd"
preamble = r'''
set -eu
failure=0
miss() { printf 'MISS %s\n' "$1"; failure=1; }
'''


class Wireless(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="mipad2-wireless-smoke-")
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.sys = self.root / "sys"
        self.lib = self.root / "lib/firmware"
        self.override = self.root / "local override"
        (self.sys / "bus/pci/devices").mkdir(parents=True)

    def file(self, directory, name, data=b"payload"):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def pci(self, name, vendor="0x14e4", device="0x43ec", driver="brcmfmac", net="wlp1s0"):
        path = self.sys / "bus/pci/devices" / name
        self.file(path, "vendor", (vendor + "\n").encode())
        self.file(path, "device", (device + "\n").encode())
        if driver:
            (path / "driver").symlink_to(f"../../drivers/{driver}")
        if net:
            (path / "net" / net / "wireless").mkdir(parents=True)
            self.file(path / "net" / net, "operstate", b"up\n")
        return path

    def invoke(self, check, *argv):
        return subprocess.run(
            ["sh", "-c", preamble + checks + "\n\"$@\"\nexit \"$failure\"\n", "test",
             check, *map(os.fspath, argv)], capture_output=True, text=True, timeout=10)

    def wifi(self):
        return self.invoke("mipad2_wifi_pci_check", self.sys)

    def firmware(self, *suffixes, override=""):
        return self.invoke("mipad2_fw_file_check", self.lib, release, override, *suffixes)

    def blobs(self, *names, folder=None):
        for name in names:
            self.file((folder or self.lib) / "brcm", name)

    def check(self, result, code, expected):
        self.assertEqual(result.returncode, code, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines(), expected)

    def test_select_onboard_not_usb_or_unrelated_pci(self):
        (self.sys / "class/net/wlan0/wireless").mkdir(parents=True)
        self.pci("0000:00:01.0", vendor="0x8086", net="external")
        self.pci("0000:01:00.0")
        self.check(self.wifi(), 0, [
            "OK   onboard BCM4356 driver brcmfmac",
            "OK   onboard Wi-Fi interface wlp1s0 (up)",
        ])

    def test_usb_only_is_not_onboard(self):
        (self.sys / "class/net/wlan0/wireless").mkdir(parents=True)
        self.check(self.wifi(), 1, ["MISS expected one onboard BCM4356 PCI device (14e4:43ec; found 0)"])

    def test_duplicate_pci_is_reported(self):
        self.pci("0000:01:00.0")
        self.pci("0000:02:00.0", net="wlp2s0")
        self.check(self.wifi(), 1, ["MISS expected one onboard BCM4356 PCI device (14e4:43ec; found 2)"])

    def test_unbound_and_interface_failure_are_distinct(self):
        path = self.pci("0000:01:00.0", driver=None, net=None)
        self.check(self.wifi(), 1, ["MISS onboard BCM4356 bound to brcmfmac"])
        (path / "driver").symlink_to("../../drivers/brcmfmac")
        self.check(self.wifi(), 1, [
            "OK   onboard BCM4356 driver brcmfmac",
            "MISS onboard BCM4356 Wi-Fi interface",
        ])

    def test_connected_and_unassociated_are_not_confused(self):
        path = self.pci("0000:01:00.0", net=None) / "net/wlan1"
        (path / "phy80211").mkdir(parents=True)
        self.file(path, "operstate", b"down\n")
        self.check(self.wifi(), 0, [
            "OK   onboard BCM4356 driver brcmfmac",
            "OK   onboard Wi-Fi interface wlan1 (down)",
        ])

    def test_board_nvram_without_wifi_binary_is_not_qualified(self):
        self.blobs(nvram, bt_patch)
        self.check(self.firmware(), 1, [
            "MISS local BCM4356 Wi-Fi firmware file (brcmfmac4356-pcie.bin)",
            "OK   local Mi Pad 2 board NVRAM file present",
            "OK   local BCM4356A2 Bluetooth firmware file present",
        ])

    def test_wifi_binary_and_generic_nvram_are_not_board_nvram(self):
        self.blobs(wifi_bin, "brcmfmac4356-pcie.txt", bt_patch)
        self.check(self.firmware(), 1, [
            "OK   local BCM4356 Wi-Fi firmware file present",
            "MISS local Mi Pad 2 board NVRAM file (brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt)",
            "OK   local BCM4356A2 Bluetooth firmware file present",
        ])

    def test_override_released_and_compressed_names(self):
        self.blobs(wifi_bin + ".zst", folder=self.override)
        self.blobs(nvram + ".xz", folder=self.lib / "updates" / release)
        self.blobs(bt_patch, folder=self.lib / release)
        self.check(self.firmware(".zst", ".xz", override=self.override), 0, [
            "OK   local BCM4356 Wi-Fi firmware file present",
            "OK   local Mi Pad 2 board NVRAM file present",
            "OK   local BCM4356A2 Bluetooth firmware file present",
        ])
        disabled = self.firmware(override=self.override)
        self.assertEqual(disabled.returncode, 1)
        self.assertEqual(disabled.stdout.count("MISS "), 2)

    def test_empty_backup_directory_and_case_mismatch_are_not_files(self):
        self.blobs(wifi_bin + ".bak", bt_patch.lower())
        self.file(self.lib / "brcm", wifi_bin, b"")
        (self.lib / "brcm" / nvram).mkdir()
        result = self.firmware(".zst", ".xz")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("MISS "), 3)
        self.assertNotIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
