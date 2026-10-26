#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compile actual HMM bodies against synthetic mapping/cache contract stubs."""
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile
import unittest


def extract(source, name):
    match = re.search(r'^(?:static )?int '+name+r'\([^;]*?\)\n\{', source, re.M)
    if not match:
        raise ValueError('Production function not found: '+name)
    start, end, depth = match.start(), match.end(), 1
    while depth:
        if end >= len(source):
            raise ValueError('Unterminated production function')
        if source[end] == '{':
            depth += 1
        if source[end] == '}':
            depth -= 1
        end += 1
    return source[start:end]


class HmmFlushContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        source = (root/'drivers/staging/media/atomisp/pci/hmm/hmm.c').read_text()
        names = ['load_and_flush_by_kmap', 'load_and_flush', 'hmm_load', 'hmm_flush']
        fixed = '\n\n'.join(extract(source, name) for name in names)
        mutated = fixed
        for buffer in ['src', 'vptr']:
            guard = '\t\tif (data)\n\t\t\tmemcpy(data, '+buffer+', bytes);'
            if mutated.count(guard) != 1:
                raise ValueError('Expected optional-copy guard changed: '+buffer)
            mutated = mutated.replace(guard, '\t\tmemcpy(data, '+buffer+', bytes);')
        template = Path(__file__).with_name('atomisp_hmm_flush_harness.c').read_text()
        if template.count('/* INSERT_PRODUCTION_FUNCTIONS */') != 1:
            raise ValueError('Harness insertion marker')
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binaries = {}
        for name, bodies in [('fixed', fixed), ('original_control', mutated)]:
            path = Path(cls.temp.name)/name
            path.with_suffix('.c').write_text(template.replace('/* INSERT_PRODUCTION_FUNCTIONS */', bodies))
            p = subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                str(path.with_suffix('.c')), '-o', str(path)], capture_output=True, text=True, timeout=30)
            if p.returncode:
                raise RuntimeError(p.stderr)
            cls.binaries[name] = path

    def run_case(self, binary, case):
        return subprocess.run([str(self.binaries[binary]), str(case)], capture_output=True, text=True, timeout=5)

    def test_fixed_copy_flush_mapping_errors_and_zero_lengths(self):
        for case in range(19):
            with self.subTest(case=case):
                result = self.run_case('fixed', case)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_nonempty_flushes_rejected_before_null_copy(self):
        for case in [0, 1, 2]:
            with self.subTest(case=case):
                self.assertEqual(self.run_case('original_control', case).returncode, 91)

    def test_other_original_mapping_and_copy_paths_unchanged(self):
        for case in range(3, 19):
            with self.subTest(case=case):
                result = self.run_case('original_control', case)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
