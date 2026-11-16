#!/usr/bin/env python3
"""Compile the actual ADC protocol header with a minimal kernel-types shim."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--cc", default="cc")
parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[3])
args = parser.parse_args()
root = args.source_root.resolve()
rows = []
with tempfile.TemporaryDirectory(prefix="chtwc-adc-tests-") as name:
    tmp = Path(name)
    (tmp/"linux").mkdir()
    (tmp/"linux/types.h").write_text("#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;\n")
    (tmp/"linux/kernel.h").write_text("#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))\n#define BIT(x) (1U << (x))\n")
    for flags in [["-O2"], ["-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]]:
        binary = tmp/f"test-{len(rows)}"
        subprocess.run([args.cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-UNDEBUG", *flags, "-I"+str(tmp),
                        "-I"+str(root/"drivers/iio/adc"),
                        str(root/"tools/testing/chtwc/test-adc.c"), "-o", str(binary)],
                       check=True, timeout=60)
        q = subprocess.run([str(binary)], check=True, capture_output=True, text=True,
                           timeout=20, env={**os.environ, "ASAN_OPTIONS":"detect_leaks=1:halt_on_error=1",
                                            "UBSAN_OPTIONS":"halt_on_error=1"})
        assert not q.stderr, q.stderr
        rows.append(dict(flags=flags, output=q.stdout.strip(), exit_code=q.returncode))
print(json.dumps(dict(tests=rows, hardware_tested=False, sources_sha256={
    p: hashlib.sha256((root/p).read_bytes()).hexdigest()
    for p in ["drivers/iio/adc/intel-chtwc-adc-core.h",
              "drivers/iio/adc/intel-chtwc-adc.c", "tools/testing/chtwc/test-adc.c"]
}), indent=2))
