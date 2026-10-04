#!/usr/bin/env python3
"""Execute actual atomic function bodies with narrow userspace atomic shims.

No hardware access. Kernel-header builds and live kernel tests remain separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]


def function(source, name):
    match = re.search(r'(?m)^static __always_inline [^\n]+\n?' +
                      r'(?:\n)?' + re.escape(name) + r'\(', source)
    if match is None:
        match = re.search(r'(?m)^static __always_inline [^\n]+ ' +
                          re.escape(name) + r'\(', source)
    assert match, name
    end = source.index('\n}', match.start()) + 2
    return source[match.start():end]


def wrapping_macro(source, name):
    start = source.index('#define ' + name + '(')
    return source[start:source.index('\n\n', start)]


def program():
    fallback = (REPO / 'include/linux/atomic/atomic-arch-fallback.h').read_text()
    generated = subprocess.check_output(['sh', 'scripts/atomic/gen-atomic-fallback.sh',
        'scripts/atomic/atomics.tbl'], cwd=REPO)
    generated += b'// ' + hashlib.sha1(generated).hexdigest().encode() + b'\n'
    assert generated == fallback.encode(), 'atomic header differs from generator output'
    overflow = (REPO / 'include/linux/overflow.h').read_text()
    functions = []
    for suffix in ('', '64'):
        for op in ('fetch_add_unless', 'inc_unless_negative', 'dec_unless_positive', 'dec_if_positive'):
            functions.append(function(fallback, 'raw_atomic' + suffix + '_' + op))
    for path, name in [('arch/x86/include/asm/atomic.h', 'arch_atomic_add_return'),
                       ('arch/x86/include/asm/atomic64_64.h', 'arch_atomic64_add_return')]:
        functions.append(function((REPO / path).read_text(), name))
    actual = '\n\n'.join(functions)
    assert 'no_sanitize' not in actual and '__signed_wrap' not in actual
    return r'''
#include <assert.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define unlikely(x) __builtin_expect(!!(x), 0)
typedef long long s64;
typedef struct { int counter; } atomic_t;
typedef struct { s64 counter; } atomic64_t;
#define raw_atomic_read(v) __atomic_load_n(&(v)->counter, __ATOMIC_SEQ_CST)
#define raw_atomic64_read raw_atomic_read
#define raw_atomic_try_cmpxchg(v, old, new) \
    __atomic_compare_exchange_n(&(v)->counter, old, new, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)
#define raw_atomic64_try_cmpxchg raw_atomic_try_cmpxchg
#define xadd(ptr, value) __atomic_fetch_add(ptr, value, __ATOMIC_SEQ_CST)
''' + wrapping_macro(overflow, 'wrapping_add') + '\n' + wrapping_macro(overflow, 'wrapping_sub') + '\n' + actual + r'''
static atomic_t shared32;
static atomic64_t shared64;
static void *worker(void *unused)
{
    (void)unused;
    for (int i = 0; i < 10000; ++i) {
        (void)arch_atomic_add_return(1, &shared32);
        (void)raw_atomic64_fetch_add_unless(&shared64, 1, 0);
    }
    return NULL;
}
#define BOUNDARIES(TYPE, PREFIX, MINIMUM, MAXIMUM, ADD) do { \
    TYPE v = { .counter = MAXIMUM }; \
    assert(ADD(1, &v) == MINIMUM && v.counter == MINIMUM); \
    assert(ADD(-1, &v) == MAXIMUM && v.counter == MAXIMUM); \
    assert(PREFIX##_fetch_add_unless(&v, 1, 0) == MAXIMUM && v.counter == MINIMUM); \
    assert(PREFIX##_fetch_add_unless(&v, -1, 0) == MINIMUM && v.counter == MAXIMUM); \
    assert(PREFIX##_fetch_add_unless(&v, 1, MAXIMUM) == MAXIMUM && v.counter == MAXIMUM); \
    v.counter = 0; \
    assert(PREFIX##_fetch_add_unless(&v, 1, 0) == 0 && v.counter == 0); \
    v.counter = MAXIMUM; \
    assert(PREFIX##_inc_unless_negative(&v) && v.counter == MINIMUM); \
    assert(!PREFIX##_inc_unless_negative(&v) && v.counter == MINIMUM); \
    assert(PREFIX##_dec_unless_positive(&v) && v.counter == MAXIMUM); \
    assert(!PREFIX##_dec_unless_positive(&v) && v.counter == MAXIMUM); \
    v.counter = 1; \
    assert(PREFIX##_dec_if_positive(&v) == 0 && v.counter == 0); \
    assert(PREFIX##_dec_if_positive(&v) == -1 && v.counter == 0); \
} while (0)
__attribute__((noinline)) static int bounds_control(int index)
{
    volatile int array[2] = {1, 2};
    return array[index];
}
int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "controls") == 0) {
        volatile int maximum = INT_MAX;
        volatile int sum = maximum + argc;
        (void)sum;
        (void)bounds_control(argc);
        return 0;
    }
    BOUNDARIES(atomic_t, raw_atomic, INT_MIN, INT_MAX, arch_atomic_add_return);
    BOUNDARIES(atomic64_t, raw_atomic64, LLONG_MIN, LLONG_MAX, arch_atomic64_add_return);
    shared32.counter = INT_MAX - 19999;
    shared64.counter = LLONG_MAX - 19999;
    pthread_t threads[4];
    for (int i = 0; i < 4; ++i) assert(pthread_create(&threads[i], NULL, worker, NULL) == 0);
    for (int i = 0; i < 4; ++i) assert(pthread_join(threads[i], NULL) == 0);
    assert(shared32.counter == INT_MIN + 20000);
    assert(shared64.counter == LLONG_MIN + 20000);
    puts("PASS 32/64-bit boundaries, unless guards and concurrent updates");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    compiler = shlex.split(args.cc)
    assert compiler and shutil.which(compiler[0]), 'C compiler required'
    source = program()
    report = dict(compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  source_sha256=hashlib.sha256(source.encode()).hexdigest(), kernel_or_hardware_test=False,
                  extracted_kernel_functions=10, tests=[])
    with tempfile.TemporaryDirectory(prefix='mipad2-atomic-wrap-') as temp:
        path = Path(temp) / 'wrap.c'
        path.write_text(source)
        binary = Path(temp) / 'wrap'
        bounds = 'array-bounds' if 'clang' in report['compiler'].lower() else 'bounds'
        command = compiler + ['-O3', '-Wall', '-Wextra', '-Werror', '-fno-strict-overflow',
            '-fsanitize=signed-integer-overflow,' + bounds, '-pthread', str(path), '-o', str(binary)]
        p = subprocess.run(command, capture_output=True, text=True, timeout=45)
        report['compile'] = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        if p.returncode == 0:
            for name, extra in [('atomic-boundaries-and-concurrency', []), ('unrelated-sanitizer-controls', ['controls'])]:
                p = subprocess.run([str(binary), *extra], capture_output=True, text=True, timeout=30)
                # GCC honors -fno-strict-overflow by omitting signed-wrap
                # diagnostics; Clang intentionally retains them. Both must
                # retain the unrelated bounds diagnostic.
                signed_expected = 'clang' in report['compiler'].lower()
                passed = p.returncode == 0 and (not p.stderr if not extra else
                    'index 2 out of bounds' in p.stderr and
                    (not signed_expected or 'signed integer overflow' in p.stderr))
                report['tests'].append(dict(name=name, exit_code=p.returncode, stdout=p.stdout,
                                           stderr=p.stderr, passed=passed,
                                           signed_control_expected=signed_expected if extra else None))
    report['all_passed'] = report['compile']['exit_code'] == 0 and len(report['tests']) == 2 and all(t['passed'] for t in report['tests'])
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
