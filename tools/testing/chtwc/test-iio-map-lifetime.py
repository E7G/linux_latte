#!/usr/bin/env python3
"""Test the real IIO lookup body with modeled unregister-at-unlock."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import resource
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--cc', required=True)
a = p.parse_args()
original = a.baseline.read_bytes()
assert hashlib.sha256(original).hexdigest() == '4ae4660286d81b199f827ad37fa906e466e25ad0e7ab534740ef99bcf6cf46ff'
current = a.source.read_bytes()


def split(data):
    start = data.index(b'static struct iio_channel *iio_channel_get_sys(')
    end = data.index(b'\nstruct iio_channel *iio_channel_get(', start)
    return data[:start], data[start:end], data[end:]


before, body, after = split(current)
old_before, old_body, old_after = split(original)
assert before == old_before and after == old_after
template = Path(__file__).with_name('test_iio_map_lifetime.c').read_bytes()
rows = []
with tempfile.TemporaryDirectory(prefix='chtwc-iio-map-test-') as raw:
    root = Path(raw)
    (root/'actual-iio-map-get.c').write_bytes(body)
    (root/'test.c').write_bytes(template)
    for index, flags in enumerate([['-O2'], ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']]):
        exe = root/f'test-{index}'
        q = subprocess.run([a.cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', *flags,
                            '-I'+str(root), str(root/'test.c'), '-o', str(exe)], capture_output=True, text=True)
        assert q.returncode == 0, q.stderr
        q = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        assert q.returncode == 0 and 'PASS 8 ' in q.stdout, (q.stdout, q.stderr)
        rows.append(dict(flags=flags, result=q.stdout.strip()))
    (root/'actual-iio-map-get.c').write_bytes(old_body)
    exe = root/'negative'
    q = subprocess.run([a.cc, '-std=gnu11', '-O1', '-fsanitize=address,undefined', '-UNDEBUG',
                        '-I'+str(root), str(root/'test.c'), '-o', str(exe)], capture_output=True, text=True)
    assert q.returncode == 0, q.stderr

    def no_core():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    q = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20, preexec_fn=no_core,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1'})
    assert q.returncode != 0 and 'heap-use-after-free' in q.stderr
print(json.dumps(dict(compiler=a.cc, tests=rows, old_body_negative_control='heap-use-after-free',
                      only_lookup_body_changed=True, source_sha256=hashlib.sha256(current).hexdigest(),
                      modeled_unregister=True, actual_kernel_concurrency_test=False)))
