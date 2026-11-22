#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Read-only Mi Pad 2 PME registration inventory. Does not test wake delivery."""
import argparse
import json
from pathlib import Path
import re

CHILD = re.compile(r"^\s*(\d+):\s+([\d\s]+)\s+INT0002 Virtual GPIO\s+2\s+ACPI:Event\s*$")


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def driver(dev):
    if not dev.is_dir():
        return "unknown", None
    node = dev / "driver"
    try:
        link = node.readlink()
    except FileNotFoundError:
        return "unbound", None
    except OSError:
        return "unknown", None
    return ("bound", link.name) if node.is_dir() else ("unknown", None)


def acpi_device(root, hid, path):
    bus = root / "sys/bus/acpi/devices"
    matches = sorted(p for p in bus.glob(f"{hid}:*") if read(p / "path") == path)
    if len(matches) != 1:
        state = "absent" if bus.is_dir() and not matches else "unknown"
        return {"matches": len(matches), "name": None, "raw_sta": None,
                "driver_state": state, "driver": None}
    dev = matches[0]
    state, name = driver(root / "sys/bus/platform/devices" / dev.name)
    return {"matches": 1, "name": dev.name, "raw_sta": read(dev / "status"),
            "uid": read(dev / "uid"), "driver_state": state, "driver": name}


def irq_state(root, irq):
    base = root / "sys/kernel/irq" / str(irq)
    return {k: read(base / k) for k in ("hwirq", "actions", "chip_name", "wakeup")}


def find_gped_child(root):
    text = read(root / "proc/interrupts")
    if not text:
        return None
    head, *rows = text.splitlines()
    cpus = head.split()
    if not cpus or not all(re.fullmatch(r"CPU\d+", c) for c in cpus):
        return None
    if len(set(cpus)) != len(cpus):
        return None
    matches = [m for row in rows if (m := CHILD.fullmatch(row))]
    if len(matches) != 1:
        return None
    irq, counts = matches[0].groups()
    vals = counts.split()
    if len(vals) != len(cpus):
        return None
    info = irq_state(root, int(irq))
    if (info["hwirq"] != "2" or info["actions"] != "ACPI:Event" or
            info["chip_name"] != "INT0002 Virtual GPIO"):
        return None
    return {"irq": int(irq), "counts": dict(zip(cpus, map(int, vals))),
            "wake_enabled": info["wakeup"] == "enabled"}


def board_inventory(root):
    gped = acpi_device(root, "INT0002", r"\_SB_.GPED")
    gpo4 = acpi_device(root, "INT33FF", r"\_SB_.GPO4")
    sci = irq_state(root, 9)
    parent = irq_state(root, 108)
    child = find_gped_child(root)
    sci_actions = {v.strip() for v in (sci["actions"] or "").split(",")}
    gped_bound = (gped["uid"] == "1" and gped["driver"] == "INT0002 Virtual GPIO"
                  if gped["matches"] == 1 else False)
    gpo4_bound = (gpo4["uid"] == "5" and gpo4["driver"] == "cherryview-pinctrl"
                  if gpo4["matches"] == 1 else False)
    if gped_bound and gpo4_bound:
        result = "both-controllers-bound"
    elif (gped_bound and gpo4["driver_state"] in {"unbound", "absent"} and child and
          sci["hwirq"] == "9" and {"acpi", "INT0002"} <= sci_actions):
        result = "gped-sci-registered"
    elif gpo4_bound:
        # A bound chip or a chv-gpio interrupt numbered 6 is not proof that
        # GPO4's specific _AEI event owns that IRQ or can wake this machine.
        result = "gpo4-bound-unverified"
    else:
        result = "no-verified-provider"
    return {"result": result, "boot_id": read(root / "proc/sys/kernel/random/boot_id"),
            "gped": gped, "gpo4": gpo4, "sci_irq9": sci,
            "gpo4_gsi108": parent, "gped_pin2_event": child,
            "wake_delivery_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = Path("/")
    if (read(root / "sys/class/dmi/id/sys_vendor") != "Xiaomi Inc" or
            read(root / "sys/class/dmi/id/product_name") != "Mipad2"):
        parser.error("not a Xiaomi Mi Pad 2")
    if not (read(root / "proc/sys/kernel/osrelease") or "").startswith("7.2."):
        parser.error("only intended for the 7.2 Mi Pad 2 kernel")
    print(json.dumps(board_inventory(root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
