#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Negative source-preparation controls, also active with Python -O."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,unittest
HERE=Path(__file__).resolve().parent
REFERENCE=None
class Preparation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mp2-public-idrt-');self.root=Path(self.temp.name)
        self.tools=self.root/'tools';self.tools.mkdir()
        for name in ['prepare_source.py','candidate.patch','manifest.json']:shutil.copyfile(HERE/name,self.tools/name)
        self.ref=self.root/'reference';self.ref.mkdir()
        m=json.loads((HERE/'manifest.json').read_text())
        for name,digest in m['baseline_files_SHA256'].items():
            if digest is not None:
                p=self.ref/name;p.parent.mkdir(exist_ok=True);shutil.copyfile(REFERENCE/name,p)
    def tearDown(self):self.temp.cleanup()
    def invoke(self,okay,output=None):
        target=output or self.root/'candidate'
        p=subprocess.run([sys.executable,str(self.tools/'prepare_source.py'),'--reference-root',str(self.ref),'--output-root',str(target)],capture_output=True,text=True,timeout=20)
        if okay:self.assertEqual(p.returncode,0,p.stderr)
        else:self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        return target,p
    def test_exact_affected_files(self):
        target,p=self.invoke(True);self.assertEqual(json.loads(p.stdout)['files'],8)
        self.assertFalse((self.ref/'src/mp2_i965_diag.c').exists())
    def test_reference_tamper_rejected(self):
        p=self.ref/'src/i965_encoder.c';p.write_bytes(p.read_bytes()+b'\n');target,_=self.invoke(False);self.assertFalse(target.exists())
    def test_existing_output_rejected_without_modification(self):
        p=self.root/'candidate';p.mkdir();(p/'sentinel').write_text('retained');self.invoke(False);self.assertEqual((p/'sentinel').read_text(),'retained')
    def test_patch_tamper_rejected_before_copy(self):
        p=self.tools/'candidate.patch';p.write_bytes(p.read_bytes()+b'\n');target,_=self.invoke(False);self.assertFalse(target.exists())
    def test_new_file_must_be_absent_in_reference(self):
        (self.ref/'src/mp2_i965_diag.c').write_text('already modified');target,_=self.invoke(False);self.assertFalse(target.exists())
    def test_reference_symlink_rejected(self):
        (self.ref/'unexpected-link').symlink_to('/etc/passwd');target,_=self.invoke(False);self.assertFalse(target.exists())
    def test_output_inside_reference_rejected(self):
        target,_=self.invoke(False,self.ref/'nested');self.assertFalse(target.exists())
    def test_dotdot_output_inside_reference_rejected(self):
        outer=self.root/'outer';outer.mkdir();target,_=self.invoke(False,outer/'..'/'reference'/'nested');self.assertFalse((self.ref/'nested').exists())
    def test_symlink_parent_output_inside_reference_rejected(self):
        link=self.root/'alias';link.symlink_to(self.ref,target_is_directory=True);target,_=self.invoke(False,link/'nested');self.assertFalse((self.ref/'nested').exists())
    def test_patched_result_pin_rejected(self):
        p=self.tools/'manifest.json';m=json.loads(p.read_text());m['candidate_files_SHA256']['src/i965_encoder.c']='0'*64;p.write_text(json.dumps(m));target,_=self.invoke(False);self.assertTrue(target.exists())
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--reference-root',required=True,type=Path);REFERENCE=p.parse_args().reference_root
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Preparation)).wasSuccessful() else 1)
