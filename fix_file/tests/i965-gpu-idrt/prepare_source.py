#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply source-only experiment to a checked, disposable reference copy."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess
def require(value,message):
    if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference-root',required=True,type=Path);p.add_argument('--output-root',required=True,type=Path);a=p.parse_args()
    here=Path(__file__).resolve().parent;m=json.loads((here/'manifest.json').read_text())
    source=a.reference_root.resolve(strict=True);target=a.output_root.resolve()
    require(source.is_dir() and not target.exists(),'Existing reference and NEW output directory required')
    require(not target.is_relative_to(source),'Output must be outside reference tree')
    require(sha(here/'candidate.patch')==m['patch_SHA256'],'Patch SHA256 mismatch')
    for name,digest in m['baseline_files_SHA256'].items():
        path=source/name
        require((not path.exists()) if digest is None else (path.is_file() and not path.is_symlink() and sha(path)==digest),'Reference mismatch: '+name)
    require(not any(x.is_symlink() for x in source.rglob('*')),'Reference symlinks not accepted')
    shutil.copytree(source,target)
    q=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(here/'candidate.patch')],cwd=target,capture_output=True,text=True)
    require(q.returncode==0,q.stdout+q.stderr)
    for name,digest in m['candidate_files_SHA256'].items():require(sha(target/name)==digest,'Patched source mismatch: '+name)
    print(json.dumps(dict(state='pinned-public-source-patch-exact',files=len(m['candidate_files_SHA256']),installed=False)))
if __name__=='__main__':main()
