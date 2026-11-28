#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the suspend shell script against simulated logind and RTC."""

import inspect
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def pmc_report(ir=0, i1=0, i2=0, i3=1000000, s0=2000000):
    return "".join(f"{name:<4} Residency:\t{value}us\n" for name, value in zip(
        ("S0IR", "S0I1", "S0I2", "S0I3", "S0"), (ir, i1, i2, i3, s0)
    ))


PMC_PERIOD = 137438953472
MOCK = f"PMC_PERIOD = {PMC_PERIOD}\n" + inspect.getsource(pmc_report) + r"""
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["FIXTURE"])
rtc = root / "sys/class/rtc/rtc0"
pmc = root / "sys/kernel/debug/pmc_atom/sleep_state"
irq = root / "sys/power/pm_wakeup_irq"
rtc_events = root / "sys/firmware/acpi/interrupts/ff_rt_clk"
interrupts = root / "proc/interrupts"
uptime = root / "proc/uptime"
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
    if mode == "replaced-before-request" and (rtc / "wakealarm").read_text():
        (rtc / "wakealarm").write_text("999\n")
    print(json.dumps({"type": "a(ssssuu)", "data": [rows]}))
elif cmd == "rtcwake":
    if args == ["-d", "/dev/rtc0", "-m", "no", "-s", "8"]:
        (rtc / "wakealarm").write_text("108\n")
        if mode == "expired-before-request":
            (rtc / "since_epoch").write_text("108\n")
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
            print("PM: suspend entry (s2idle)")
            if mode == "mixed-pme-and-rtc":
                print("ACPI: PM: ACPI custom handler wakeup")
            elif mode == "fixed-debug":
                print("ACPI: PM: ACPI fixed event wakeup")
            print("PM: suspend exit")
            if count == 3:
                log("resume")
                (rtc / "since_epoch").write_text("107\n" if mode == "early-clock" else "108\n")
                irq.write_text("127\n" if mode == "button" else "9\n")
                if mode not in ("shared-sci-only", "button", "early-clock"):
                    counter = {"multiple-rtc": "5", "reset-counter": "0",
                               "bad-counter-after": "invalid"}.get(mode, "4")
                    rtc_events.write_text(f"       {counter}    disabled     unmasked\n")
                lines = interrupts.read_text().splitlines(keepends=True)
                if mode == "silent-pme-and-rtc":
                    lines[-1] = lines[-1].replace("3 0 0 0", "3 0 1 0")
                elif mode == "redistributed-pme":
                    lines[-1] = lines[-1].replace("3 0 0 0", "2 1 0 0")
                elif mode == "changed-pme-irq":
                    lines[-1] = lines[-1].replace("131:", "133:")
                elif mode == "missing-pme-after":
                    lines.pop()
                elif mode == "changed-pme-cpus":
                    lines[0] = lines[0].replace("CPU2", "CPU4")
                elif mode == "bad-pme-after":
                    lines[-1] = lines[-1].replace("3 0 0 0", "bad 0 0 0")
                elif mode == "duplicate-pme-after":
                    lines.append(" 133: 3 0 0 0 INT0002 Virtual GPIO 2 ACPI:Event\n")
                interrupts.write_text("".join(lines))
                uptime.write_text({
                    "clock-backwards": "99.99 1.00\n",
                    "long-window": "140000.00 1.00\n",
                }.get(mode, "108.00 1.00\n"))
                if mode == "rollover":
                    report = pmc_report(i3=5200000, s0=1500000)
                elif mode == "s0-only":
                    report = pmc_report(s0=10388608)
                elif mode == "pmc-reset":
                    report = pmc_report(i3=0)
                elif mode == "pmc-jump":
                    report = pmc_report(i3=20000000)
                elif mode == "overflow-after":
                    report = pmc_report(i1=18446744073709551616)
                else:
                    report = pmc_report(i2=160000, i3=7200000, s0=4000000)
                if mode == "duplicate-pmc-after":
                    report += "S0I3 Residency:\t7200000us\n"
                if mode != "no-residency":
                    pmc.write_text(report)
                if mode == "foreign-alarm":
                    (rtc / "wakealarm").write_text("999\n")
            elif mode == "late-audio-failure":
                print("warm DSP resume failed; forcing cold restart (timeout)")
elif cmd == "sleep":
    assert "clear\n" not in (root / "events").read_text(), "RTC cleared before resume"
elif cmd in ("mkdir", "rmdir", "cat"):
    import shutil
    trace_parent = root / "sys/kernel/tracing/instances"
    path = Path(args[0])
    uuid = "0123456789abcdef0123456789abcdef"
    instance = trace_parent / ("mipad2-pmc-" + uuid)
    if cmd == "mkdir":
        if path != instance:
            raise RuntimeError("unexpected instance root")
        path.mkdir()
        for part in ("events/pmc_atom/pmc_atom_s2idle", "events/power/suspend_resume"):
            (path/part).mkdir(parents=True)
            (path/part/"enable").write_text("0\n")
        (path/"trace").touch()
    elif cmd == "rmdir":
        if path != instance:
            raise RuntimeError("unexpected trace cleanup root")
        for part in ("events/pmc_atom/pmc_atom_s2idle", "events/power/suspend_resume"):
            if (path/part/"enable").read_text() != "0\n":
                raise RuntimeError("trace cleanup left an event enabled")
        shutil.rmtree(path)
    elif path == instance/"trace":
        marker = (instance/"trace_marker").read_text().strip()
        if (instance/"tracing_on").read_text() != "0\n":
            raise RuntimeError("trace must be frozen before export")
        if (instance/"trace_clock").read_text() != "global\n":
            raise RuntimeError("expected common clock in private instance")
        for part in ("events/pmc_atom/pmc_atom_s2idle", "events/power/suspend_resume"):
            if (instance/part/"enable").read_text() != "1\n":
                raise RuntimeError("missing private event enable")
        steps = [("tracing_mark_write", f"mipad2-pmc:{uuid}:begin")]
        if marker == f"mipad2-pmc:{uuid}:end":
            steps.extend([("suspend_resume", "suspend_enter[1] begin"),
                          ("suspend_resume", "suspend_enter[1] end"),
                          ("pmc_atom_s2idle", "func_dis=0x00000001 func_dis_2=0x00000002 "
                           "d3_sts_0=0x00000003 d3_sts_1=0x00000004 pss=0x00000005 forced_clks=0x00000000"),
                          ("suspend_resume", "machine_suspend[1] begin"),
                          ("suspend_resume", "machine_suspend[1] end"),
                          ("suspend_resume", "console_resume_all[1] begin"),
                          ("suspend_resume", "console_resume_all[1] end"),
                          ("tracing_mark_write", marker)])
        elif marker != f"mipad2-pmc:{uuid}:begin":
            raise RuntimeError("missing capture marker")
        print(f"# entries-in-buffer/entries-written: {len(steps)}/{len(steps)}   #P:4")
        for n, (event, value) in enumerate(steps):
            print(f" task-101 [000] .... {n}.00: {event}: {value}")
    else:
        print(path.read_text(), end="")
elif cmd == "mipad2-hardware-smoke":
    raise RuntimeError("capture and preflight must never probe media")
"""


def check_case(source, mode, expected_code, expected_events, expected_alarm, options=(), capture=None):
    with tempfile.TemporaryDirectory(prefix="mipad2-suspend-host-") as temp:
        root = Path(temp)
        files = {
            "sys/class/dmi/id/sys_vendor": "Xiaomi Inc\n",
            "sys/class/dmi/id/product_name": "Other\n" if mode == "wrong-device" else "Mipad2\n",
            "proc/1/comm": "systemd\n",
            "proc/uptime": "unavailable\n" if mode == "clock-malformed" else "100.00 0.50\n",
            "proc/interrupts": (
                "      CPU0 CPU1 CPU2 CPU3\n"
                "   9: 1 0 0 0 IO-APIC 9-fasteoi acpi, INT0002\n"
                + ("" if mode == "no-pme-child" else
                   " 131: 3 0 0 0 INT0002 Virtual GPIO 2 ACPI:Event\n")
            ),
            "sys/power/mem_sleep": "[s2idle]\n",
            "sys/power/pm_wakeup_irq": "",
            "sys/kernel/debug/pmc_atom/sleep_state": {
                "rollover": pmc_report(i3=PMC_PERIOD - 1000000, s0=PMC_PERIOD - 500000),
                "missing-pmc-before": "S0I3 Residency:\t1000000us\n",
                "duplicate-pmc-before": pmc_report() + "S0  Residency:\t0us\n",
                "overflow-before": pmc_report(i3=PMC_PERIOD),
                "misaligned-before": pmc_report(i3=1000001),
                "invalid-unit-before": pmc_report().replace("1000000us", "1000000ms"),
            }.get(mode, pmc_report()),
            "sys/class/rtc/rtc0/wakealarm": "555\n" if mode == "prearmed" else "",
            "sys/class/rtc/rtc0/since_epoch": "100\n",
            "sys/firmware/acpi/interrupts/ff_rt_clk":
                "malformed\n" if mode == "bad-counter-before" else "       3    disabled     unmasked\n",
            "events": "",
        }
        if mode == "duplicate-pme":
            files["proc/interrupts"] += " 133: 0 0 0 0 INT0002 Virtual GPIO 2 ACPI:Event\n"
        if mode == "missing-counter":
            del files["sys/firmware/acpi/interrupts/ff_rt_clk"]
        for name, value in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)

        (root / "run").mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        commands = ["id", "busctl", "rtcwake", "systemctl", "journalctl", "sleep"]
        if options:
            trace = root/"sys/kernel/tracing"
            (trace/"instances").mkdir(parents=True)
            for part in ("events/pmc_atom/pmc_atom_s2idle", "events/power/suspend_resume"):
                (trace/part).mkdir(parents=True)
                (trace/part/"format").touch()
                (trace/part/"enable").write_text("0\n")
            if mode == "trace-globally-enabled":
                (trace/"events/pmc_atom/pmc_atom_s2idle/enable").write_text("1\n")
            if mode == "trace-unavailable":
                (trace/"events/pmc_atom/pmc_atom_s2idle/format").unlink()
            uuid=root/"proc/sys/kernel/random/uuid"
            uuid.parent.mkdir(parents=True)
            uuid.write_text("01234567-89ab-cdef-0123-456789abcdef\n")
            commands += ["cat", "mkdir", "rmdir", "mipad2-hardware-smoke"]
        for name in commands:
            prog = bindir / name
            prog.write_text(f"#!{sys.executable}\n" + MOCK)
            prog.chmod(0o700)

        # Keep fixture paths out of the production script's interface.
        script = root / "run-test.sh"
        script.write_text(re.sub(r"(?<!\w)/(sys/|proc/|run/)", lambda m: f"{root}/{m[1]}", source))
        env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin", FIXTURE=str(root), CASE=mode)
        result = subprocess.run(
            ["/bin/sh", str(script), *options], env=env, text=True, capture_output=True, timeout=24,
        )
        events = (root / "events").read_text().splitlines()
        alarm = (root / "sys/class/rtc/rtc0/wakealarm").read_text().strip()
        if (result.returncode, events, alarm) != (expected_code, expected_events, expected_alarm):
            raise AssertionError((mode, result.returncode, events, alarm, result.stdout, result.stderr))
        if options:
            expected_global = "1\n" if mode == "trace-globally-enabled" else "0\n"
            if (trace/"events/pmc_atom/pmc_atom_s2idle/enable").read_text() != expected_global:
                raise AssertionError("the global trace setting changed")
            if list((trace/"instances").iterdir()):
                raise AssertionError("a private trace instance was left behind")
            if options == ("--preflight",):
                if list((root/"run").iterdir()) or (not expected_code and "no suspend requested" not in result.stdout):
                    raise AssertionError((mode, result.stdout, result.stderr, "preflight changed state"))
            receipts = list((root/"run").glob("mipad2-pmc-capture.*"))
            if capture is None:
                if receipts or "PMC_CAPTURE_DIR=" in result.stdout:
                    raise AssertionError((mode, "unexpected trace receipt"))
            else:
                if len(receipts) != 1 or f"PMC_CAPTURE_DIR={receipts[0]}\n" not in result.stdout:
                    raise AssertionError((mode, result.stdout, result.stderr))
                import runpy
                report = runpy.run_path(str(Path(__file__).with_name("mipad2-pmc-s2idle-report.py")))
                trace_text = (receipts[0]/"pmc.trace").read_text()
                log_text = (receipts[0]/"rtc.log").read_text()
                if capture == "incomplete":
                    if "\nPM" in trace_text or ":end" in trace_text:
                        raise AssertionError((mode, "unexpected completion marker"))
                    try:
                        report["capture_report"](trace_text, log_text)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError((mode, "false complete capture"))
                else:
                    checked = report["capture_report"](trace_text, log_text)
                    if (checked["s0i3_threshold_met"] != (capture == "met") or
                            "physical media smoke not run" not in log_text):
                        raise AssertionError((mode, checked, log_text))
            return
        wake_failures = {
            "shared-sci-only": "without corroborating evidence of an RTC wake",
            "mixed-pme-and-rtc": "Kernel reported a different wake source",
            "silent-pme-and-rtc": "Virtual PME child interrupt evidence changed",
            "redistributed-pme": "Virtual PME child interrupt evidence changed",
            "changed-pme-irq": "Virtual PME child interrupt evidence changed",
            "changed-pme-cpus": "Virtual PME child interrupt evidence changed",
            "missing-pme-after": "Virtual PME child interrupt evidence changed",
            "duplicate-pme-after": "Cannot read virtual PME interrupt counters after resume",
        }
        if mode in wake_failures:
            if wake_failures[mode] not in result.stderr or "INFO S0I3 delta:" not in result.stdout:
                raise AssertionError((mode, result.stdout, result.stderr))
        evidence = {
            "normal": ("S0IR delta:  0us", "S0I1 delta:  0us", "S0I2 delta:  160000us",
                       "S0I3 delta:  6200000us", "S0 delta:  2000000us"),
            "rollover": ("S0I3 delta:  6200000us (modulo counter period)",
                         "S0 delta:  2000000us (modulo counter period)"),
            "s0-only": ("S0 delta:  8388608us", "S0I3 residency increased only 0us"),
        }
        for line in evidence.get(mode, ()):
            if line not in result.stdout:
                raise AssertionError((mode, line, result.stdout, result.stderr))
        diagnostics = {
            "clock-malformed": "Invalid PMC residency snapshot before suspend",
            "missing-pmc-before": "Invalid PMC residency snapshot before suspend",
            "duplicate-pmc-before": "Invalid PMC residency snapshot before suspend",
            "overflow-before": "Invalid PMC residency snapshot before suspend",
            "misaligned-before": "Invalid PMC residency snapshot before suspend",
            "invalid-unit-before": "Invalid PMC residency snapshot before suspend",
            "duplicate-pmc-after": "Invalid PMC residency snapshot after resume",
            "overflow-after": "Invalid PMC residency snapshot after resume",
            "clock-backwards": "Boot-time clock moved backwards",
            "long-window": "does not exclude a full counter period",
            "pmc-reset": "PMC residency deltas exceed the measured boot-time window: S0I3",
            "pmc-jump": "PMC residency deltas exceed the measured boot-time window: S0I3",
        }
        if mode in diagnostics and diagnostics[mode] not in result.stderr:
            raise AssertionError((mode, result.stdout, result.stderr))


if __name__ == "__main__":
    script = Path(__file__).with_name("mipad2-suspend-test.sh").read_text()
    cases = (
        ("normal", 0, ["arm", "request", "resume", "clear"], ""),
        ("rollover", 0, ["arm", "request", "resume", "clear"], ""),
        ("s0-only", 1, ["arm", "request", "resume", "clear"], ""),
        ("pmc-reset", 1, ["arm", "request", "resume", "clear"], ""),
        ("pmc-jump", 1, ["arm", "request", "resume", "clear"], ""),
        ("overflow-after", 1, ["arm", "request", "resume", "clear"], ""),
        ("duplicate-pmc-after", 1, ["arm", "request", "resume", "clear"], ""),
        ("clock-backwards", 1, ["arm", "request", "resume", "clear"], ""),
        ("long-window", 1, ["arm", "request", "resume", "clear"], ""),
        ("clock-malformed", 1, [], ""),
        ("missing-pmc-before", 1, [], ""),
        ("duplicate-pmc-before", 1, [], ""),
        ("overflow-before", 1, [], ""),
        ("misaligned-before", 1, [], ""),
        ("invalid-unit-before", 1, [], ""),
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
        ("fixed-debug", 0, ["arm", "request", "resume", "clear"], ""),
        ("shared-sci-only", 1, ["arm", "request", "resume", "clear"], ""),
        ("mixed-pme-and-rtc", 1, ["arm", "request", "resume", "clear"], ""),
        ("silent-pme-and-rtc", 1, ["arm", "request", "resume", "clear"], ""),
        ("redistributed-pme", 1, ["arm", "request", "resume", "clear"], ""),
        ("changed-pme-irq", 1, ["arm", "request", "resume", "clear"], ""),
        ("changed-pme-cpus", 1, ["arm", "request", "resume", "clear"], ""),
        ("missing-pme-after", 1, ["arm", "request", "resume", "clear"], ""),
        ("duplicate-pme-after", 1, ["arm", "request", "resume", "clear"], ""),
        ("bad-pme-after", 1, ["arm", "request", "resume", "clear"], ""),
        ("duplicate-pme", 1, [], ""),
        ("no-pme-child", 1, [], ""),
        ("multiple-rtc", 1, ["arm", "request", "resume", "clear"], ""),
        ("reset-counter", 1, ["arm", "request", "resume", "clear"], ""),
        ("bad-counter-after", 1, ["arm", "request", "resume", "clear"], ""),
        ("bad-counter-before", 1, [], ""),
        ("missing-counter", 1, [], ""),
        ("expired-before-request", 1, ["arm", "clear"], ""),
        ("replaced-before-request", 1, ["arm"], "999"),
    )
    for case in cases:
        check_case(script, *case)
    print(f"PASS: {len(cases)} suspend, PMC residency, inhibitor, RTC ownership and wake-source cases")
    extra = (
        ("normal", 0, [], "", ("--preflight",), None),
        ("blocked", 1, [], "", ("--preflight",), None),
        ("prearmed", 1, [], "555", ("--preflight",), None),
        ("trace-globally-enabled", 1, [], "", ("--capture", "8"), None),
        ("trace-unavailable", 1, [], "", ("--capture", "8"), None),
        ("normal", 0, ["arm", "request", "resume", "clear"], "", ("--capture", "8"), "met"),
        ("s0-only", 1, ["arm", "request", "resume", "clear"], "", ("--capture", "8"), "missed"),
        ("late-inhibitor", 1, ["arm", "clear"], "", ("--capture", "8"), "incomplete"),
        ("no-resume", 1, ["arm", "request"], "108", ("--capture", "8"), "incomplete"),
    )
    for case in extra:
        check_case(script, *case)
    print(f"PASS: {len(extra)} read-only preflight and isolated capture cases")
