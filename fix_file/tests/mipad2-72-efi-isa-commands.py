#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the actual cached Kbuild commands from an early-boot CI build."""
import argparse
from pathlib import Path
import shlex

TARGETS = (
    ("arch/x86/boot/compressed/.misc.o.cmd", "x86-64"),
    ("drivers/firmware/efi/libstub/.x86-stub.o.cmd", "x86-64"),
    ("init/.main.o.cmd", "silvermont"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("wrapper", type=Path)
    args = parser.parse_args()
    wrapper = str(args.wrapper.resolve(strict=True))
    for path, expected in TARGETS:
        lines = (args.build / path).read_text().splitlines()
        commands = [line.split(" := ", 1)[1] for line in lines
                    if line.startswith(("savedcmd_", "cmd_")) and " := " in line]
        if len(commands) != 1:
            raise SystemExit(f"{path}: missing or ambiguous compiler command")
        command = shlex.split(commands[0])
        if not command or command[0] != wrapper:
            raise SystemExit(f"{path}: expected compiler wrapper {wrapper}")
        # Kbuild may append an objtool command after the compile recipe.
        flags = []
        for token in command[1:]:
            if token == ";":
                break
            if token.startswith("-march="):
                flags.append(token.split("=", 1)[1])
        if not flags or flags[-1] != expected:
            raise SystemExit(f"{path}: expected final -march={expected}, got {flags!r}")
        print(f"{path}: final -march={flags[-1]}")


if __name__ == "__main__":
    main()
