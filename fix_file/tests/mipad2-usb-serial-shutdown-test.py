#!/usr/bin/env python3
"""Run the shipped serial helper with fake sysfs and a fixture job list."""
import os
from pathlib import Path
import subprocess
import tempfile


def check(condition, reason):
    if not condition:
        raise RuntimeError(reason)


root = Path(__file__).resolve().parents[1] / "packages/mipad2-usb-serial"
helper = (root / "mipad2-usb-serial-quiesce").read_text()
unit = (root / "mipad2-usb-serial-quiesce.service").read_text()
check("After=mipad2-usb-serial.service serial-getty@ttyGS0.service\n" in unit, "must stop before getty and gadget")
check("ExecStop=/usr/local/libexec/mipad2-usb-serial-quiesce\n" in unit, "bad quiesce command")
check("Wants=mipad2-usb-serial-quiesce.service\n" in (root / "60-shutdown-quiesce.conf").read_text(), "missing late service")

with tempfile.TemporaryDirectory(prefix="mipad2-serial-shutdown-") as tmp:
    fixture = Path(tmp)
    gadget = fixture / "mipad2"
    bound = gadget / "UDC"
    config = gadget / "configs/c.1/acm.usb0"
    function = gadget / "functions/acm.usb0"
    config.parent.mkdir(parents=True)
    function.mkdir(parents=True)
    config.symlink_to(function, target_is_directory=True)
    (gadget / "idVendor").write_text("0x1d6b\n")
    (gadget / "idProduct").write_text("0x0104\n")
    (function / "console").write_text("1\n")
    neutral = "dwc3.0.auto\n"
    script = fixture / "helper"
    generic = "G=/sys/kernel/config/usb_gadget/mipad2\n"
    check(helper.count(generic) == 1, "unsafe fixture substitution")
    script.write_text(helper.replace(generic, f"G={gadget}\n"))
    fake = fixture / "systemctl"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$MOCK_JOBS"\nexit "$MOCK_STATUS"\n')
    fake.chmod(0o755)
    (fixture / "id").write_text('#!/bin/sh\n[ "$1" = -u ] && echo 0\n')
    (fixture / "id").chmod(0o755)

    def run(jobs, *, detach=False, status=0, value=neutral):
        bound.write_text(value)
        env = dict(os.environ, PATH=f"{fixture}:{os.environ['PATH']}",
                   MOCK_JOBS=jobs, MOCK_STATUS=str(status))
        result = subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True, timeout=4)
        check(result.returncode == 0, result.stderr)
        check(bound.read_text() == ("\n" if detach else value), f"unexpected UDC for {jobs!r}")

    run("12 serial-getty@ttyGS0.service stop running")
    run("13 sleep.target start waiting\n14 suspend.target start waiting")
    run("13 shutdown.target stop running")
    run("14 fail-reboot.target start waiting")
    run("12 shutdown.target start waiting", status=1)
    for name in ("shutdown", "reboot", "poweroff", "halt", "kexec"):
        run(f"14 {name}.target start waiting", detach=True)
    check((function / "console").read_text() == "1\n", "quiesce must not alter the console attribute")
    run("11 reboot.target start waiting", value="\n")
    (gadget / "idVendor").write_text("0xffff\n")
    run("11 reboot.target start waiting")
    (gadget / "idVendor").write_text("0x1d6b\n")
    config.unlink()
    run("11 reboot.target start waiting")
print("PASS serial shutdown-only job gating, ownership, order and preserved console attribute")
