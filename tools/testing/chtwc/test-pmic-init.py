#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the unchanged actual installer with synchronous ACPI/fault stubs.

Not an AML interpreter, kernel build, PMIC hardware or thermal-policy test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def structure(text, name):
    start = text.index("struct " + name + " {")
    end = text.index("\n};", start) + len("\n};")
    return text[start:end] + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    source = ROOT / "drivers/acpi/pmic/intel_pmic.c"
    header = ROOT / "drivers/acpi/pmic/intel_pmic.h"
    text = source.read_text()
    start = text.index("int intel_pmic_install_opregion_handler(")
    end = text.index("\nEXPORT_SYMBOL_GPL(intel_pmic_install_opregion_handler);", start)
    function = text[start:end]
    types = structure(header.read_text(), "intel_pmic_opregion_data")
    types += structure(text, "intel_pmic_regs_handler_ctx")
    types += structure(text, "intel_pmic_opregion")
    types += "static struct intel_pmic_opregion *intel_pmic_opregion;\n"
    test = Path(__file__).with_suffix(".c")
    results = []
    with tempfile.TemporaryDirectory(prefix="mipad2-pmic-init-") as directory:
        tmp = Path(directory)
        under_test = tmp / "pmic-installer-under-test.h"
        under_test.write_text(types + function)
        for name, flags in [("O2", ["-O2"]), ("sanitizers", ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"])]:
            binary = tmp / name
            subprocess.run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", *flags,
                            "-I", str(tmp), str(test), "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            results.append(dict(build=name, summary=result.stdout.strip()))
        # Restore precisely the old late-assignment behavior. The same test must
        # fail, demonstrating that the callback is actually observed during install.
        assignment = "\topregion->data = d;\n"
        if function.count(assignment) != 1:
            raise RuntimeError("Unexpected installer assignment; review negative control")
        late = function.replace(assignment, "").replace("\tintel_pmic_opregion = opregion;", assignment + "\tintel_pmic_opregion = opregion;")
        if late == function:
            raise RuntimeError("Late-assignment negative control did not change source")
        under_test.write_text(types + late)
        binary = tmp / "old-order"
        subprocess.run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-I", str(tmp), str(test), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        if result.returncode != 64 or "ctx->data == &data" not in result.stderr:
            raise RuntimeError("Old-order control did not fail at reentry: " + result.stderr)
    print(json.dumps(dict(compiler=args.cc, results=results, old_order_negative_control=True,
                         source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                         hardware_tested=False), indent=2))


if __name__ == "__main__":
    main()
