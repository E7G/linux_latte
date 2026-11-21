#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Temporary logind sleep/idle inhibitor for a Mi Pad 2 serial debug session."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

UNIT = "mipad2-serial-debug-awake.service"
WHO = "MiPad2-serial-debug"
WHY = "User requested awake during serial debugging"
PROPERTIES = ("LoadState", "ActiveState", "Transient", "MainPID",
              "ActiveEnterTimestamp", "RuntimeMaxUSec")


def run(argv):
    result = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=12)
    return result.stdout


class Guard:
    def __init__(self, command=run, wait=time.sleep):
        self.command = command
        self.wait = wait

    def unit(self):
        return dict(line.split("=", 1) for line in self.command(
            ["systemctl", "show", UNIT, *(f"-p{x}" for x in PROPERTIES)]
        ).splitlines())

    def held(self, unit):
        if (unit["LoadState"] != "loaded" or unit["ActiveState"] != "active"
                or unit["Transient"] != "yes" or int(unit["MainPID"]) <= 0
                or unit["RuntimeMaxUSec"] in ("", "infinity")):
            return False
        reply = json.loads(self.command([
            "busctl", "--system", "--timeout=5s", "--json=short", "call",
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", "ListInhibitors",
        ]))
        data = reply["data"]
        if reply["type"] != "a(ssssuu)" or len(data) != 1 or not isinstance(data[0], list):
            raise ValueError("unexpected logind inhibitor response")
        for row in data[0]:
            if (isinstance(row, list) and len(row) == 6
                    and isinstance(row[0], str) and set(row[0].split(":")) == {"sleep", "idle"}
                    and row[1:4] == [WHO, WHY, "block"]
                    and type(row[4]) is int and row[4] == 0
                    and type(row[5]) is int and row[5] == int(unit["MainPID"])):
                return True
        return False

    def check(self):
        unit = self.unit()
        if not self.held(unit):
            raise ValueError("serial debug sleep/idle lock is not verified")
        return unit

    def start(self, minutes):
        unit = self.unit()
        if self.held(unit):
            return unit, False
        if unit["LoadState"] != "not-found":
            raise ValueError(f"{UNIT} already exists but its lock is not verified")

        seconds = 60 * minutes
        self.command([
            "systemd-run", f"--unit={UNIT}", "--collect", "--service-type=exec",
            "--property=After=systemd-logind.service",
            "--property=Wants=systemd-logind.service",
            f"--property=RuntimeMaxSec={seconds + 5}s",
            "/usr/bin/systemd-inhibit", "--what=sleep:idle", "--mode=block",
            f"--who={WHO}", f"--why={WHY}", "/usr/bin/sleep", str(seconds),
        ])
        # Type=exec proves execve, not successful acquisition from logind.
        for _ in range(10):
            unit = self.unit()
            if self.held(unit):
                return unit, True
            self.wait(0.2)
        raise ValueError("service started but logind did not confirm the debug lock")

    def stop(self):
        self.check()
        self.command(["systemctl", "stop", UNIT])


def timeout_minutes(value):
    minutes = int(value)
    if not 1 <= minutes <= 120:
        raise argparse.ArgumentTypeError("minutes must be between 1 and 120")
    return minutes


def show_status(unit):
    print(f"Serial debug lock held since {unit['ActiveEnterTimestamp']} "
          f"(maximum runtime {unit['RuntimeMaxUSec']}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="verify the live logind lock; make no changes")
    start = commands.add_parser("start", help="prevent auto sleep for 1-120 minutes")
    start.add_argument("minutes", type=timeout_minutes)
    commands.add_parser("stop", help="release only the verified serial debug lock")
    args = parser.parse_args()
    guard = Guard()
    try:
        if args.command == "status":
            show_status(guard.check())
            return
        if os.geteuid() != 0:
            raise ValueError("run start/stop with sudo")
        dmi = Path("/sys/class/dmi/id")
        if ((dmi / "sys_vendor").read_text().strip() != "Xiaomi Inc"
                or (dmi / "product_name").read_text().strip() != "Mipad2"):
            raise ValueError("start/stop is limited to a Xiaomi Mi Pad 2")
        fd = os.open("/run/mipad2-serial-debug-command.lock",
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == "start":
                unit, started = guard.start(args.minutes)
                if not started:
                    print("Existing lock left in place; its runtime was not extended.")
                show_status(unit)
            else:
                guard.stop()
                print("Serial debug lock released.")
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{parser.prog}: {getattr(exc, 'stderr', None) or exc}\n")


if __name__ == "__main__":
    main()
