#!/usr/bin/env python3
"""Executable false-positive regression tests for the live DSP log gate."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "dsp_log_check", Path(__file__).with_name("mipad2_tfa_dsp_log_check.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
MARKER = "MIPAD2_TFA_DSP_BEGIN_123456"


def containers():
    return "\n".join(
        f"[2] tfa98xx {dev}: factory container ready: left profiles=3 defer_dsp_start=0"
        for dev in module.DEVICES) + "\n"


def result(dev, ret):
    return f"[3] tfa98xx {dev}: factory DSP init ret={ret} profile=0 vstep=0\n"


class LogGateTests(unittest.TestCase):
    def test_both_current_successes(self):
        text = MARKER + "\n" + containers()
        text += "".join(result(dev, 0) for dev in module.DEVICES)
        self.assertEqual(module.check(text, MARKER), dict.fromkeys(module.DEVICES, 0))

    def test_historical_success_is_not_current_evidence(self):
        text = containers() + "".join(result(dev, 0) for dev in module.DEVICES)
        text += MARKER + "\n" + containers()
        with self.assertRaises(ValueError):
            module.check(text, MARKER)

    def test_one_amp_success_cannot_pass(self):
        text = MARKER + "\n" + containers() + result(module.DEVICES[0], 0)
        with self.assertRaises(ValueError):
            module.check(text, MARKER)

    def test_latest_failure_overrides_earlier_success(self):
        text = MARKER + "\n" + containers()
        text += "".join(result(dev, 0) for dev in module.DEVICES)
        text += result(module.DEVICES[1], -110)
        with self.assertRaises(ValueError):
            module.check(text, MARKER)

    def test_missing_or_duplicate_marker(self):
        for text in (containers(), MARKER + "\n" + MARKER + "\n" + containers()):
            with self.assertRaises(ValueError):
                module.check(text, MARKER)

    def test_container_only_is_separate_gate(self):
        text = MARKER + "\n" + containers()
        self.assertEqual(module.check(text, MARKER, containers_only=True), {})
        with self.assertRaises(ValueError):
            module.check(text, MARKER)

    def test_safe_probe_is_not_active_factory_init(self):
        text = (MARKER + "\n" + containers()).replace("defer_dsp_start=0", "defer_dsp_start=1")
        with self.assertRaises(ValueError):
            module.check(text, MARKER, containers_only=True)

    def test_unrelated_device_or_message_cannot_supply_success(self):
        text = MARKER + "\n" + containers()
        text += result("i2c-tfa9890:02", 0)
        text += "unrelated factory DSP init ret=0\n"
        with self.assertRaises(ValueError):
            module.check(text, MARKER)


if __name__ == "__main__":
    unittest.main()
