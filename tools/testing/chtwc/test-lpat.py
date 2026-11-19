#!/usr/bin/env python3
"""Actual conversion + extracted loader/read_raw, mock ACPI/IRQ; not hardware."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--cc', default='cc')
args = parser.parse_args()
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
root = Path(__file__).resolve().parents[3]
driver = (root / 'drivers/iio/adc/intel-chtwc-adc.c').read_text()
units = (root / 'include/linux/units.h').read_text()
constant = re.search(r'^#define ABSOLUTE_ZERO_MILLICELSIUS -273150$', units, re.M)
assert constant

def function(name):
    start = driver.index('static int ' + name + '(')
    begin = driver.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (driver[end] == '{') - (driver[end] == '}')
        end += 1
    return driver[start:end] + '\n'

# ABI exposure is a source gate; actual full kernel build remains separate.
probe = function('chtwc_adc_probe')
assert re.search(r'devm_iio_device_alloc\(dev,\s*struct_size\(adc, channels,\s*'
                 r'ARRAY_SIZE\(chtwc_iio_channels\)\)\)', probe)
assert 'memcpy(adc->channels, chtwc_iio_channels, sizeof(chtwc_iio_channels))' in probe
assert 'for (i = 5; i <= 7; i++)' in probe
assert 'adc->channels[i].info_mask_separate |= BIT(IIO_CHAN_INFO_PROCESSED)' in probe
assert 'indio_dev->channels = adc->channels;' in probe
assert 'acpi_evaluate_integer' not in driver and '"_TMP"' not in driver
rows = []
with tempfile.TemporaryDirectory(prefix='chtwc-lpat-') as name:
    tmp = Path(name)
    (tmp / 'linux').mkdir()
    shims = {
        'types.h': '#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef int64_t s64;\n',
        'kernel.h': '#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))\n#define BIT(x) (1U << (x))\n',
        'limits.h': '#include <limits.h>\n',
        'math64.h': '#include <stdint.h>\nstatic inline int64_t div_s64(int64_t n, int32_t d) { return n / d; }\n',
        'units.h': constant[0] + '\n',
    }
    for path, text in shims.items():
        (tmp / 'linux' / path).write_text(text)
    (tmp / 'actual-lpat-loader.c').write_text(function('chtwc_adc_load_lpat'))
    (tmp / 'actual-read-raw.c').write_text(function('chtwc_adc_read_raw'))
    for flags in [['-O2'], ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']]:
        binary = tmp / ('test-' + str(len(rows)))
        command = [args.cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-parameter', '-UNDEBUG', *flags,
                   '-I' + str(tmp), '-I' + str(root / 'drivers/iio/adc'),
                   str(root / 'tools/testing/chtwc/test-lpat.c'), '-o', str(binary)]
        subprocess.run(command, check=True, timeout=60)
        q = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60,
                           env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1',
                                'UBSAN_OPTIONS': 'halt_on_error=1'})
        assert q.returncode == 0 and not q.stderr, q.stdout + q.stderr
        rows.append(dict(flags=flags, output=q.stdout.strip()))
    # Actual result path must reject a firmware method without executing it.
    # This mutant removes only the constant-package guard and must fail.
    path = tmp / 'actual-lpat-loader.c'
    original = path.read_text()
    assert original.count(' || type != ACPI_TYPE_PACKAGE') == 1
    path.write_text(original.replace(' || type != ACPI_TYPE_PACKAGE', ''))
    mutant = tmp / 'method-mutant'
    subprocess.run([args.cc, '-std=gnu11', '-O2', '-UNDEBUG', '-I' + str(tmp),
                    '-I' + str(root / 'drivers/iio/adc'),
                    str(root / 'tools/testing/chtwc/test-lpat.c'), '-o', str(mutant)],
                   check=True, timeout=60)
    q = subprocess.run([str(mutant)], capture_output=True, timeout=30)
    assert q.returncode != 0, 'Method-evaluation negative control passed unexpectedly'
paths = ['drivers/iio/adc/intel-chtwc-adc.c', 'drivers/iio/adc/intel-chtwc-adc-core.h',
         'drivers/iio/adc/intel-chtwc-adc-lpat.h', 'tools/testing/chtwc/test-lpat.c',
         'tools/testing/chtwc/test-lpat.py', 'tools/testing/chtwc/lpat-fixture.h']
print(json.dumps(dict(compiler=args.cc, tests=rows, method_negative_control=True,
                      mocked_acpi=True, hardware_tested=False,
                      sha256={p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                              for p in paths}), indent=2))
