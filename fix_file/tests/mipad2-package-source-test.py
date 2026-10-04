#!/usr/bin/env python3
"""Exercise helper package source/checksum staging without makepkg or installs."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PACKAGES = Path(__file__).resolve().parents[1] / 'packages'
READ_METADATA = r'''
set -eu
source "$1"
declare -p source sha256sums >/dev/null
printf 'SOURCE\t%s\n' "${source[@]}"
printf 'SHA256\t%s\n' "${sha256sums[@]}"
'''
STAGE = r'''
set -eu
source "$1"
srcdir="$2"
pkgdir="$3"
cd "$srcdir"
package
'''

class PackageSources(unittest.TestCase):
    def test_clean_source_staging_all_packages(self):
        recipes = sorted(PACKAGES.glob('*/PKGBUILD'))
        self.assertEqual(len(recipes), 6)
        for recipe in recipes:
            with self.subTest(package=recipe.parent.name):
                # Stage only declared sources, not any pre-existing src/ tree.
                p = subprocess.run(['bash', '-c', READ_METADATA, 'metadata', str(recipe)],
                                   capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                sources = [line.split('\t', 1)[1] for line in p.stdout.splitlines()
                           if line.startswith('SOURCE\t')]
                sums = [line.split('\t', 1)[1] for line in p.stdout.splitlines()
                        if line.startswith('SHA256\t')]
                self.assertTrue(sources)
                self.assertEqual(len(sources), len(sums))
                self.assertEqual(len(set(sources)), len(sources))
                with tempfile.TemporaryDirectory(prefix='mipad2-package-source-test-') as temp:
                    temp = Path(temp)
                    srcdir = temp / 'src'
                    pkgdir = temp / 'pkg'
                    srcdir.mkdir()
                    pkgdir.mkdir()
                    for name, digest in zip(sources, sums):
                        self.assertEqual(name, Path(name).name, 'Keep local sources beside PKGBUILD')
                        path = recipe.parent / name
                        self.assertTrue(path.is_file(), name)
                        self.assertFalse(path.is_symlink(), name)
                        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, name)
                        shutil.copyfile(path, srcdir / name)
                    p = subprocess.run(['bash', '-c', STAGE, 'stage', str(recipe), str(srcdir), str(pkgdir)],
                                       capture_output=True, text=True, timeout=30)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    payload = [p for p in pkgdir.rglob('*') if p.is_file()]
                    self.assertTrue(payload)
                    source_hashes = {hashlib.sha256((srcdir / s).read_bytes()).hexdigest() for s in sources}
                    for path in payload:
                        self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), source_hashes)
                        self.assertTrue(path.relative_to(pkgdir).parts[0] in ('usr', 'etc'))

if __name__ == '__main__':
    unittest.main()
