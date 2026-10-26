#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Source-extracted Gen8 PIPE_CONTROL packet tests; no GPU access or installs."""
from pathlib import Path
import argparse,hashlib,re,subprocess,tempfile,unittest
PINS={'i965_gpe_utils.c':'95622c7b837a91f8da51463f00860c088c2e9e2918a48b1c6b6f3c7529cadf60','i965_gpe_utils.h':'584c26617ad9f204da39f0210dd6fe420c0cde36d31ff96618c1583b36cf529c','intel_driver.h':'7ab5693626f4a2281760006fb0de98e7e359459c4aff5455cfdb4d1cbb0621ea'}
ARGS=None
def require(value,message):
    if not value:raise ValueError(message)
def function(text,name):
    a=text.index('\n'+name+'(');start=text.rfind('\nvoid',0,a)+1;br=text.index('{',a);depth=0
    for m in re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]',text[br:],re.S):
        if m[0].startswith(('/*','//','"')):continue
        depth+=1 if m[0]=='{' else -1
        if not depth:return text[start:br+m.end()]
    raise ValueError('Unclosed function')

PRE=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"packet check line %d: %s\n",__LINE__,#x);exit(3);}}while(0)
typedef void *VADriverContextP;
typedef struct { uint64_t address; } dri_bo;
struct intel_batchbuffer { uint32_t words[6]; unsigned n,read,write; };
static void out(struct intel_batchbuffer *b,uint32_t value){CHECK(b->n<6);b->words[b->n++]=value;}
static void reloc(struct intel_batchbuffer *b,dri_bo *bo,unsigned read,unsigned write,unsigned offset){
 CHECK(bo);b->read=read;b->write=write;uint64_t address=bo->address+offset;out(b,(uint32_t)address);out(b,(uint32_t)(address>>32));
}
#define __OUT_BATCH(B,V) out((B),(uint32_t)(V))
#define __OUT_RELOC64(B,O,R,W,X) reloc((B),(O),(R),(W),(X))
#define I915_GEM_DOMAIN_RENDER 0x2
#define I915_GEM_DOMAIN_INSTRUCTION 0x10
'''
MAIN=r'''
static uint32_t seed=0xa5116a35U;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
int main(int argc,char **argv){
 dri_bo bo={0x12345678fff00000ULL};unsigned disables[]={0,1,2,UINT_MAX};unsigned count=0;
 CHECK(argc==2);
 if(!strcmp(argv[1],"original-negative")){
  struct intel_batchbuffer b={0};struct gpe_pipe_control_parameter p={0};original_control(NULL,&b,&p);
  if(!(b.words[1]&CMD_PIPE_CONTROL_CS_STALL)){fputs("original emits depth-flush bit0 instead of CS_STALL bit20\n",stderr);return 7;}
  return 0;
 }
 for(unsigned d=0;d<4;d++)for(unsigned mode=0;mode<3;mode++)for(unsigned target=0;target<2;target++)for(unsigned sample=0;sample<256;sample++){
  struct gpe_pipe_control_parameter p={0};p.disable_cs_stall=disables[d];p.flush_mode=mode;p.bo=target?&bo:NULL;p.offset=(next()&0xfffffff8U);p.dw0=next();p.dw1=next();
  struct intel_batchbuffer old={0},fixed={0};original_control(NULL,&old,&p);gen8_gpe_pipe_control(NULL,&fixed,&p);
  CHECK(old.n==6 && fixed.n==6);CHECK(fixed.words[0]==(CMD_PIPE_CONTROL|(6-2)));
  CHECK(!!(fixed.words[1]&CMD_PIPE_CONTROL_CS_STALL)==!p.disable_cs_stall);
  CHECK(!(fixed.words[1]&CMD_PIPE_CONTROL_DEPTH_CACHE_FLUSH));
  uint32_t expected=old.words[1];if(!p.disable_cs_stall)expected=(expected&~CMD_PIPE_CONTROL_DEPTH_CACHE_FLUSH)|CMD_PIPE_CONTROL_CS_STALL;
  CHECK(fixed.words[1]==expected);
  for(unsigned i=0;i<6;i++)if(i!=1)CHECK(old.words[i]==fixed.words[i]);
  CHECK(old.read==fixed.read && old.write==fixed.write);
  CHECK(fixed.words[4]==p.dw0 && fixed.words[5]==p.dw1);
  if(target){uint64_t address=bo.address+p.offset;CHECK(fixed.words[2]==(uint32_t)address && fixed.words[3]==(uint32_t)(address>>32));CHECK(fixed.read==(I915_GEM_DOMAIN_RENDER|I915_GEM_DOMAIN_INSTRUCTION) && fixed.write==I915_GEM_DOMAIN_RENDER);}
  else CHECK(fixed.words[2]==0 && fixed.words[3]==0);
  count++;
 }
 CHECK(count==6144);puts("6144-source-extracted-packets-pass-all-other-words-domains-and-relocations-preserved");return 0;
}
'''

class CSStall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources={}
        for name,expected in PINS.items():
            raw=(Path(ARGS.source_root)/'src'/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==expected,'Unexpected reference '+name);cls.sources[name]=raw.decode()
        cls.tmp=tempfile.TemporaryDirectory(prefix='mipad2-CS-stall-');cls.root=Path(cls.tmp.name);(cls.root/'src').mkdir()
        p=cls.root/'src/i965_gpe_utils.c';p.write_text(cls.sources['i965_gpe_utils.c'])
        q=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(Path(ARGS.patch).resolve())],cwd=cls.root,capture_output=True,text=True);require(q.returncode==0,q.stdout+q.stderr)
        cls.fixed=p.read_text();cls.original=cls.sources['i965_gpe_utils.c']
        macro_lines=[s for s in cls.sources['intel_driver.h'].splitlines() if s.startswith('#define CMD_3D ') or s.startswith('#define CMD_PIPE_CONTROL')]
        header=cls.sources['i965_gpe_utils.h'];macro_lines += [s for s in header.splitlines() if s.startswith('#define PIPE_CONTROL_FLUSH_')]
        a=header.index('struct gpe_pipe_control_parameter {');z=header.index('\n};',a)+3;params=header[a:z]
        license=cls.original[:cls.original.index('*/')+2]
        cls.harness=license+'\n'+PRE+'\n'+'\n'.join(macro_lines)+'\n'+params+'\n'+function(cls.original,'gen8_gpe_pipe_control').replace('gen8_gpe_pipe_control','original_control')+'\n'+function(cls.fixed,'gen8_gpe_pipe_control')+'\n'+MAIN
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def compile_run(self,name,flags=(),negative=False):
        p=self.root/(name+'.c');p.write_text(self.harness);exe=self.root/name
        q=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*flags,str(p),'-o',str(exe)],capture_output=True,text=True);self.assertEqual(q.returncode,0,q.stderr)
        q=subprocess.run([str(exe),'original-negative' if negative else 'fixed'],capture_output=True,text=True,timeout=15)
        if negative:self.assertEqual(q.returncode,7);self.assertIn('instead of CS_STALL bit20',q.stderr)
        else:self.assertEqual(q.returncode,0,q.stderr);self.assertIn('6144-source-extracted-packets-pass',q.stdout)
    def test_normal_packets(self):self.compile_run('normal')
    def test_ndebug_packets(self):self.compile_run('ndebug',['-DNDEBUG'])
    def test_ubsan_packets(self):self.compile_run('ubsan',['-fsanitize=undefined','-fno-sanitize-recover=all'])
    def test_original_must_fail_bit20_check(self):self.compile_run('original-negative',negative=True)
    def test_only_source_line_changes(self):
        self.assertEqual(self.fixed.replace('int cs_stall_enable = param->disable_cs_stall ? 0 : CMD_PIPE_CONTROL_CS_STALL;','int cs_stall_enable = !param->disable_cs_stall;'),self.original)
    def test_source_bits_are_not_boolean_positions(self):
        self.assertRegex(self.sources['intel_driver.h'],r'CMD_PIPE_CONTROL_CS_STALL\s+\(1 << 20\)');self.assertRegex(self.sources['intel_driver.h'],r'CMD_PIPE_CONTROL_DEPTH_CACHE_FLUSH\s+\(1 << 0\)')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',required=True);p.add_argument('--patch',default=str(Path(__file__).with_name('gen8-CS-stall.patch')));ARGS=p.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CSStall));raise SystemExit(0 if result.wasSuccessful() else 1)
