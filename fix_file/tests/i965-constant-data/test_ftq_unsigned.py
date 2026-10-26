#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile the actual FTQ block from a pinned reference plus source-only patch."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,tempfile,unittest

REFERENCE_SHA256='ad43b90c33505293386f53ff7f5ec44eee28c6e1392915a6b0583bf6354e4f82'
ARGS=None

def require(value,message):
    if not value:raise ValueError(message)

def block_at(text,start):
    opening=text.index('{',start);depth=0
    for m in re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]',text[opening:],re.S):
        if m[0].startswith(('/*','//','"')):continue
        depth+=1 if m[0]=='{' else -1
        if not depth:return text[start:opening+m.end()]
    raise ValueError('Unclosed source block')

def ftq(text):
    start=text.index('gen9_avc_load_mb_brc_const_data(')
    function=block_at(text,start)
    return block_at(function,function.index('if (avc_state->ftq_skip_threshold_lut_input_enable)'))

HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"%d %s\n",__LINE__,#x);exit(3);}}while(0)
struct state { uint8_t ftq_skip_threshold_lut[52];unsigned ftq_skip_threshold_lut_input_enable; };
static void apply(uint32_t *out,const uint8_t *lut,unsigned enabled) {
 struct state s;memcpy(s.ftq_skip_threshold_lut,lut,52);s.ftq_skip_threshold_lut_input_enable=enabled;
 struct state *avc_state=&s;unsigned int *data=out;int i;
 for(i=0;i<52;i++) { __BLOCK__
 data+=16;
 }
}
int main(void) {
 uint32_t out[834];uint8_t lut[52];
 for(unsigned byte=0;byte<256;byte++)for(unsigned enabled=0;enabled<2;enabled++) {
  for(unsigned i=0;i<834;i++)out[i]=0x8d9a7c31U^i;
  for(unsigned i=0;i<52;i++)lut[i]=byte;
  apply(out+1,lut,enabled);
  for(unsigned i=0;i<834;i++) {
   uint32_t want=0x8d9a7c31U^i;unsigned slot=i?((i-1)%16):0;
   if(enabled && i>0 && i<833 && (slot==6 || slot==7)) {
    uint32_t v=byte;want=v|(v<<16)|(v<<24);
    if(slot==7)want|=v<<8;
   }
   CHECK(out[i]==want);
  }
 }
 puts("all256bytes-two-enable-modes-832words-and-two-canaries-pass");return 0;
}
'''

class FTQUnsigned(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference=Path(ARGS.reference).read_bytes()
        require(hashlib.sha256(cls.reference).hexdigest()==REFERENCE_SHA256,'Unexpected reference SHA256')
        cls.tmp=tempfile.TemporaryDirectory(prefix='mipad2-i965-ftq-')
        cls.root=Path(cls.tmp.name);(cls.root/'src').mkdir()
        p=cls.root/'src/i965_avc_encoder.c';p.write_bytes(cls.reference)
        q=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(Path(ARGS.patch).resolve())],cwd=cls.root,capture_output=True,text=True)
        require(q.returncode==0,'Exact patch failed: '+q.stdout+q.stderr)
        cls.fixed=p.read_text();cls.original=cls.reference.decode()
        cls.old_block=ftq(cls.original);cls.fixed_block=ftq(cls.fixed)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_c(self,name,block,flags=(),unsafe=False):
        p=self.root/(name+'.c');p.write_text(HARNESS.replace('__BLOCK__',block));exe=self.root/name
        q=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',*flags,str(p),'-o',str(exe)],capture_output=True,text=True)
        self.assertEqual(q.returncode,0,q.stderr)
        q=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        if unsafe:
            self.assertNotEqual(q.returncode,0)
            self.assertIn('left shift of 128 by 24',q.stderr)
        else:
            self.assertEqual(q.returncode,0,q.stderr)
            self.assertEqual(q.stdout.strip(),'all256bytes-two-enable-modes-832words-and-two-canaries-pass')

    def test_patch_only_changes_unsigned_promotions(self):
        self.assertEqual(self.fixed_block.count('(uint32_t)avc_state->ftq_skip_threshold_lut[i] <<'),5)
        self.assertEqual(self.fixed.replace('(uint32_t)avc_state->ftq_skip_threshold_lut[i] <<','avc_state->ftq_skip_threshold_lut[i] <<'),self.original)

    def test_all_bytes_normal(self):self.run_c('normal',self.fixed_block)
    def test_all_bytes_ndebug(self):self.run_c('ndebug',self.fixed_block,['-DNDEBUG'])
    def test_all_bytes_ubsan(self):self.run_c('ubsan',self.fixed_block,['-fsanitize=undefined','-fno-sanitize-recover=all'])
    def test_actual_original_is_required_negative(self):
        self.run_c('original-negative',self.old_block,['-fsanitize=undefined','-fno-sanitize-recover=all'],unsafe=True)
    def test_first_unsafe_shift_regression_is_detected(self):
        b=self.fixed_block.replace('((uint32_t)avc_state->ftq_skip_threshold_lut[i] << 24)','(avc_state->ftq_skip_threshold_lut[i] << 24)',1)
        self.assertNotEqual(b,self.fixed_block)
        self.run_c('first-negative',b,['-fsanitize=undefined','-fno-sanitize-recover=all'],unsafe=True)
    def test_second_unsafe_shift_regression_is_detected(self):
        token='((uint32_t)avc_state->ftq_skip_threshold_lut[i] << 24)';pos=self.fixed_block.rindex(token)
        b=self.fixed_block[:pos]+self.fixed_block[pos:].replace(token,'(avc_state->ftq_skip_threshold_lut[i] << 24)',1)
        self.run_c('second-negative',b,['-fsanitize=undefined','-fno-sanitize-recover=all'],unsafe=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True,help='Pinned irql 2.4.5 src/i965_avc_encoder.c')
    parser.add_argument('--patch',default=str(Path(__file__).with_name('ftq-unsigned-shifts.patch')))
    ARGS=parser.parse_args()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FTQUnsigned)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
