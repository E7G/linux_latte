#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "report", Path(__file__).with_name("mipad2-pstore-report.py"))
pstore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pstore)

STAMP = 1795123456
NAMES = [f"dmesg-efi_pstore-{STAMP * 100000 + part * 1000 + 1}"
         for part in range(1, 4)]


class PstoreReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.live = self.root / "live"
        self.archive = self.root / "archive"
        self.live.mkdir()
        self.archive.mkdir()

    def report(self, mounted=True):
        return pstore.report(self.live, self.archive, mounted)

    def test_live_and_systemd_archive_deduplicate_without_exposing_logs(self):
        data = b"Panic#1 Part1\nprivate-hostname and serial"
        archived = self.archive / str(STAMP) / "001"
        archived.mkdir(parents=True)
        old_name = NAMES[0].replace("efi_pstore", "efi")
        (self.live / NAMES[0]).write_bytes(data)
        (archived / old_name).write_bytes(data)
        (archived / NAMES[1]).write_bytes(b"Panic#1 Part2\ntail")
        (archived / "dmesg.txt").write_bytes(b"Panic#1 Part1\ncombined duplicate")
        result = self.report()
        self.assertEqual(result["live"]["records"], 1)
        self.assertEqual(result["archive"]["records"], 2)
        self.assertEqual(result["efi_groups"], [
            {"record_epoch_seconds": STAMP, "dump_count": 1,
             "chunks_by_header": {"panic": 2}},
        ])
        self.assertNotIn("private-hostname", json.dumps(result))
        self.assertEqual((self.live / NAMES[0]).read_bytes(), data)
        self.assertEqual((archived / old_name).read_bytes(), data)

    def test_compressed_and_unknown_are_not_claimed_as_panic(self):
        (self.live / (NAMES[0] + ".enc.z")).write_bytes(b"Panic#1 Part1\n")
        (self.live / NAMES[1]).write_bytes(b"untrusted\nPanic#1 Part2\n")
        (self.live / NAMES[2]).write_bytes(b"Oops#1 Part3\n")
        (self.live / "dmesg-erst-1234567").write_bytes(b"Panic#1 Part1\n")
        result = self.report()
        self.assertEqual(result["efi_groups"][0]["chunks_by_header"],
                         {"compressed": 1, "unknown": 1, "oops": 1})

    def test_same_id_different_contents_not_deduplicated(self):
        (self.live / NAMES[0]).write_bytes(b"Panic#1 Part1\none")
        (self.archive / NAMES[0]).write_bytes(b"Panic#1 Part1\ntwo")
        self.assertEqual(self.report()["efi_groups"][0]["chunks_by_header"], {"panic": 2})

    def test_archive_only_dump_can_span_two_wall_clock_seconds(self):
        for stamp, part in ((STAMP, 1), (STAMP + 1, 2)):
            group = self.archive / str(stamp) / "001"
            group.mkdir(parents=True)
            name = f"dmesg-efi_pstore-{stamp * 100000 + part * 1000 + 1}"
            (group / name).write_text(f"Panic#1 Part{part}\n")
        result = self.report()
        self.assertEqual(result["live"]["state"], "empty")
        self.assertEqual(result["archive"]["state"], "records")
        self.assertEqual(result["efi_groups"], [
            {"record_epoch_seconds": stamp, "dump_count": 1,
             "chunks_by_header": {"panic": 1}}
            for stamp in (STAMP, STAMP + 1)
        ])

    def test_missing_empty_and_unmounted_distinct(self):
        self.archive.rmdir()
        self.assertEqual(self.report()["archive"]["state"], "missing")
        self.assertEqual(self.report()["live"]["state"], "empty")
        (self.live / NAMES[0]).write_bytes(b"Panic#1 Part1\n")
        self.assertEqual(self.report(mounted=False)["live"]["state"], "not-mounted")
        self.assertEqual(self.report(mounted=False)["efi_groups"], [])

    def test_symlink_and_fifo_never_read_or_descended(self):
        external = self.root / "not-pstore"
        external.mkdir()
        (external / NAMES[1]).write_bytes(b"Panic#1 Part2\n")
        (self.live / NAMES[0]).symlink_to(external / NAMES[1])
        (self.archive / str(STAMP)).symlink_to(external, target_is_directory=True)
        os.mkfifo(self.live / NAMES[2])
        result = self.report()
        self.assertEqual(result["live"]["state"], "partial")
        self.assertEqual(result["live"]["errors"], 2)
        self.assertEqual(result["archive"]["state"], "partial")
        self.assertEqual(result["efi_groups"], [])

    def test_symlink_source_is_unreadable(self):
        self.archive.rmdir()
        self.archive.symlink_to(self.live, target_is_directory=True)
        self.assertEqual(self.report()["archive"]["state"], "unreadable")

    def test_read_race_and_oversize_report_partial(self):
        (self.live / NAMES[0]).write_bytes(b"Panic#1 Part1\n" + b"x" * pstore.MAX_BYTES)
        (self.live / NAMES[1]).touch()
        original = pstore.read_record

        def read_record(fd, name):
            if name == NAMES[1]:
                (self.live / name).unlink()
            return original(fd, name)

        with mock.patch.object(pstore, "read_record", side_effect=read_record):
            result = self.report()
        self.assertEqual(result["live"]["errors"], 2)
        self.assertEqual(result["live"]["state"], "partial")
        self.assertEqual(result["efi_groups"], [])

    def test_budget_is_shared_across_archive_tree(self):
        archived = self.archive / str(STAMP) / "001"
        archived.mkdir(parents=True)
        (archived / NAMES[0]).touch()
        with mock.patch.object(pstore, "MAX_ENTRIES", 2):
            result = self.report()
        self.assertTrue(result["archive"]["scan_limit_hit"])
        self.assertEqual(result["archive"]["state"], "partial")

    def test_mountinfo_requires_real_pstore_at_expected_path(self):
        self.assertTrue(pstore.pstore_mounted(
            "26 23 0:21 / /sys/fs/pstore ro,nosuid shared:1 - pstore pstore ro"))
        self.assertFalse(pstore.pstore_mounted(
            "26 23 0:21 / /sys/fs/pstore rw - tmpfs tmpfs rw\n"
            "27 23 0:22 / /tmp/other rw - pstore pstore rw\n"
            "malformed"))


if __name__ == "__main__":
    unittest.main()
