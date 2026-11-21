#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the suspend shell script against simulated logind and RTC."""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


MOCK = r"""
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["FIXTURE"])
rtc = root / "sys/class/rtc/rtc0"
pmc = root / "sys/kernel/debug/pmc_atom/sleep_state"
irq = root / "sys/power/pm_wakeup_irq"
cmd = Path(sys.argv[0]).name
args = sys.argv[1:]
mode = os.environ["CASE"]

def log(line):
    with (root / "events").open("a") as stream:
        stream.write(line + "\n")

if cmd == "id":
    print(0)
elif cmd == "busctl":
    assert "ListInhibitors" in args
    rows = [["sleep", "NetworkManager", "prepare for sleep", "delay", 0, 15]]
    if mode == "blocked" or (mode == "late-inhibitor" and (rtc / "wakealarm").read_text()):
        rows.append(["sleep:idle", "MiPad2-serial-debug", "serial debugging", "block", 0, 22])
    if mode == "bad-inhibitors":
        rows.append(["sleep", "broken"])
    print(json.dumps({"type": "a(ssssuu)", "data": [rows]}))
elif cmd == "rtcwake":
    if args == ["-d", "/dev/rtc0", "-m", "no", "-s", "8"]:
        (rtc / "wakealarm").write_text("108\n")
        log("arm")
    elif args == ["-d", "/dev/rtc0", "-m", "disable"]:
        (rtc / "wakealarm").write_text("")
        log("clear")
    else:
        raise RuntimeError(f"unsupported RTC invocation: {args}")
elif cmd == "systemctl":
    assert args == ["--check-inhibitors=yes", "suspend"]
    log("request")
    if mode == "request-unknown":
        raise SystemExit(1)
elif cmd == "journalctl":
    if "--show-cursor" in args:
        print("Previous kernel data\n-- cursor: KERNEL_CURSOR")
    else:
        assert "--after-cursor=KERNEL_CURSOR" in args
        assert "request\n" in (root / "events").read_text()
        status = root / "journal_reads"
        count = int(status.read_text()) + 1 if status.exists() else 1
        status.write_text(str(count))
        if mode == "missing-journal":
            raise SystemExit(1)
        if mode == "no-entry" or count == 1:
            pass
        elif mode == "no-resume" or count == 2:
            print("PM: suspend entry (s2idle)")
        elif mode == "ambiguous":
            print("PM: suspend entry (s2idle)\nPM: suspend exit\n"
                  "PM: suspend entry (s2idle)\nPM: suspend exit")
        else:
            print("PM: suspend entry (s2idle)\nPM: suspend exit")
            if count == 3:
                log("resume")
                (rtc / "since_epoch").write_text("107\n" if mode == "early-clock" else "108\n")
                irq.write_text("127\n" if mode == "button" else "9\n")
                if mode != "no-residency":
                    pmc.write_text("S0I3 Residency:\t7200000us\n")
                if mode == "foreign-alarm":
                    (rtc / "wakealarm").write_text("999\n")
            elif mode == "late-audio-failure":
                print("warm DSP resume failed; forcing cold restart (timeout)")
elif cmd == "sleep":
    assert "clear\n" not in (root / "events").read_text(), "RTC cleared before resume"
"""


def check_case(source, mode, expected_code, expected_events, expected_alarm):
    with tempfile.TemporaryDirectory(prefix="mipad2-suspend-host-") as temp:
        root = Path(temp)
        files = {
            "sys/class/dmi/id/sys_vendor": "Xiaomi Inc\n",
            "sys/class/dmi/id/product_name": "Other\n" if mode == "wrong-device" else "Mipad2\n",
            "proc/1/comm": "systemd\n",
            "sys/power/mem_sleep": "[s2idle]\n",
            "sys/power/pm_wakeup_irq": "",
            "sys/kernel/debug/pmc_atom/sleep_state": "S0I3 Residency:\t1000000us\n",
            "sys/class/rtc/rtc0/wakealarm": "555\n" if mode == "prearmed" else "",
            "sys/class/rtc/rtc0/since_epoch": "100\n",
            "events": "",
        }
        for name, value in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)

        (root / "run").mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        for name in ("id", "busctl", "rtcwake", "systemctl", "journalctl", "sleep"):
            prog = bindir / name
            prog.write_text(f"#!{sys.executable}\n" + MOCK)
            prog.chmod(0o700)

        # Keep fixture paths out of the production script's interface.
        script = root / "run-test.sh"
        script.write_text(re.sub(r"(?<!\w)/(sys/|proc/|run/)", lambda m: f"{root}/{m[1]}", source))
        env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin", FIXTURE=str(root), CASE=mode)
        result = subprocess.run(
            ["/bin/sh", str(script)], env=env, text=True, capture_output=True, timeout=12,
        )
        events = (root / "events").read_text().splitlines()
        alarm = (root / "sys/class/rtc/rtc0/wakealarm").read_text().strip()
        assert (result.returncode, events, alarm) == (expected_code, expected_events, expected_alarm), (
            mode, result.returncode, events, alarm, result.stdout, result.stderr
        )


if __name__ == "__main__":
    script = Path(__file__).with_name("mipad2-suspend-test.sh").read_text()
    for case in (
        ("normal", 0, ["arm", "request", "resume", "clear"], ""),
        ("blocked", 1, [], ""),
        ("bad-inhibitors", 1, [], ""),
        ("wrong-device", 1, [], ""),
        ("late-inhibitor", 1, ["arm", "clear"], ""),
        ("prearmed", 1, [], "555"),
        ("request-unknown", 1, ["arm", "request"], "108"),
        ("missing-journal", 1, ["arm", "request"], "108"),
        ("no-entry", 1, ["arm", "request"], "108"),
        ("no-resume", 1, ["arm", "request"], "108"),
        ("ambiguous", 1, ["arm", "request"], "108"),
        ("button", 1, ["arm", "request", "resume", "clear"], ""),
        ("early-clock", 1, ["arm", "request", "resume", "clear"], ""),
        ("foreign-alarm", 0, ["arm", "request", "resume"], "999"),
        ("no-residency", 1, ["arm", "request", "resume", "clear"], ""),
        ("late-audio-failure", 1, ["arm", "request", "resume", "clear"], ""),
    ):
        check_case(script, *case)
    print("PASS: 16 suspend, inhibitor, RTC ownership and journal cases")
