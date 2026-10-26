#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Source-extracted GPU IDRT packet/ownership tests. No GPU or device access."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,tempfile,unittest
ARGS=None
def require(v,msg):
 if not v:raise ValueError(msg)
def block(text,needle):
 a=text.index(needle);br=text.index('{',a);depth=0
 for m in re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]',text[br:],re.S):
  if m[0].startswith(('/*','//','"')):continue
  depth+=1 if m[0]=='{' else -1
  if depth==0:return text[a:br+m.end()]
 raise ValueError('Unclosed source block')
def fn(text,name):
 m=re.search(r'(?:static\s+)?(?:void|int)\s*\n'+name+r'\(',text);require(m is not None,'Missing function '+name)
 return block(text[m.start():],m[0])

PRE=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <assert.h>
#define CHECK(X) do {if(!(X)){fprintf(stderr,"line%d %s\n",__LINE__,#X);exit(3);}}while(0)
#define ALIGN(i,n) (((i)+(n)-1)&~((n)-1))
#define I915_GEM_DOMAIN_RENDER 0x2
#define I915_GEM_DOMAIN_INSTRUCTION 0x10
typedef void *VADriverContextP;
typedef struct {uint64_t size,offset64;void *virtual;} dri_bo;
struct intel_batchbuffer {uint32_t words[64];unsigned n,relocs,offsets[8],reads[8],writes[8];dri_bo *bos[8];};
static unsigned maps,unmaps;
static void dri_bo_map(dri_bo *bo,int write){CHECK(bo && bo->virtual && write==1);maps++;}
static void dri_bo_unmap(dri_bo *bo){CHECK(bo);unmaps++;}
static void out(struct intel_batchbuffer *b,uint32_t v){CHECK(b->n<64);b->words[b->n++]=v;}
static void reloc(struct intel_batchbuffer *b,dri_bo *bo,unsigned read,unsigned write,unsigned offset){
 CHECK(bo && b->relocs<8);unsigned j=b->relocs++;b->bos[j]=bo;b->offsets[j]=offset;b->reads[j]=read;b->writes[j]=write;
 uint64_t a=bo->offset64+offset;out(b,(uint32_t)a);out(b,(uint32_t)(a>>32));
}
#define __OUT_BATCH(B,V) out((B),(uint32_t)(V))
#define __OUT_RELOC64(B,O,R,W,X) reloc((B),(O),(R),(W),(X))
'''
MAIN=r'''
static uint32_t seed=0xb44b19e7;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void valid(struct i965_gpe_context *g,dri_bo *bo){
 memset(g,0,sizeof(*g));g->num_kernels=1;g->idrt.max_entries=1;g->idrt.entry_size=64;g->idrt.offset=1024;
 g->idrt.bo=g->curbe.bo=g->dynamic_state.bo=bo;g->dynamic_state.bo_size=4096;g->curbe.length=512;
}
int main(void){
 unsigned count=0;
 for(unsigned sample=0;sample<4096;sample++){
  unsigned char cpu[4096],gpu[4096];for(unsigned i=0;i<4096;i++)cpu[i]=gpu[i]=(unsigned char)next();
  dri_bo old={4096,0x1234fffff000ULL+(sample%4)*4096ULL,cpu},new={4096,old.offset64,gpu};
  struct i965_gpe_context a,b;valid(&a,&old);a.curbe.offset=(sample%4)*64;a.curbe.length=1+next()%1536;a.idrt.offset=ALIGN(a.curbe.offset+a.curbe.length,64);
  a.sampler.offset=a.idrt.offset+64;a.kernels[0].kernel_offset=next()&~63U;a.surface_state_binding_table.binding_table_offset=(next()&2047U)<<5;
  b=a;b.idrt.bo=b.curbe.bo=b.dynamic_state.bo=&new;struct i965_gpe_context snapshot=b;
  unsigned oldmaps=maps;gen8_gpe_setup_interface_data(NULL,&a);CHECK(maps==oldmaps+1 && unmaps==maps);
  struct intel_batchbuffer batch={0};CHECK(mp2_gen8_gpu_idrt_upload(NULL,&b,&batch)==1);CHECK(maps==oldmaps+1 && unmaps==maps);
  CHECK(!memcmp(&snapshot,&b,sizeof(b)));CHECK(batch.n==30 && batch.relocs==4);
  for(unsigned i=0;i<5;i++)CHECK(batch.words[6*i]==(CMD_PIPE_CONTROL|(6-2)));
  for(unsigned i=0;i<4;i++){
   unsigned j=6*i;uint32_t expected=CMD_PIPE_CONTROL_CS_STALL|CMD_PIPE_CONTROL_WC_FLUSH|CMD_PIPE_CONTROL_DC_FLUSH|CMD_PIPE_CONTROL_WRITE_QWORD|CMD_PIPE_CONTROL_LOCAL_PGTT_GEN8|CMD_PIPE_CONTROL_FLUSH_ENABLE;
   CHECK(batch.words[j+1]==expected && !(batch.words[j+1]&CMD_PIPE_CONTROL_DEPTH_CACHE_FLUSH));
   CHECK(batch.bos[i]==&new && batch.offsets[i]==b.idrt.offset+8*i && !(batch.offsets[i]&7));
   CHECK(batch.reads[i]==(I915_GEM_DOMAIN_RENDER|I915_GEM_DOMAIN_INSTRUCTION) && batch.writes[i]==I915_GEM_DOMAIN_RENDER);
   uint64_t address=(uint64_t)batch.words[j+2]|((uint64_t)batch.words[j+3]<<32);CHECK(address==new.offset64+batch.offsets[i]);
   memcpy(gpu+batch.offsets[i],&batch.words[j+4],8);
  }
  uint32_t readbits=CMD_PIPE_CONTROL_CS_STALL|CMD_PIPE_CONTROL_WC_FLUSH|CMD_PIPE_CONTROL_SC_INVALIDATION_GEN8|CMD_PIPE_CONTROL_CC_INVALIDATION_GEN8|CMD_PIPE_CONTROL_VFC_INVALIDATION_GEN8|CMD_PIPE_CONTROL_IS_FLUSH|CMD_PIPE_CONTROL_GLOBAL_GTT_GEN8|CMD_PIPE_CONTROL_FLUSH_ENABLE;
  CHECK(batch.words[25]==readbits);for(unsigned i=26;i<30;i++)CHECK(batch.words[i]==0);
  CHECK(!memcmp(cpu,gpu,sizeof(cpu)));count++;
 }
 CHECK(count==4096);
 unsigned char storage[4096];memset(storage,0xa5,sizeof(storage));dri_bo bo={4096,0x1234fffff000ULL,storage},other=bo;
 CHECK(!mp2_gen8_gpu_idrt_eligible(NULL));CHECK(!mp2_gen8_gpu_idrt_upload(NULL,NULL,NULL));
 for(unsigned mode=0;mode<22;mode++){
  struct i965_gpe_context g;valid(&g,&bo);struct intel_batchbuffer batch={0};
  switch(mode){
   case 0:g.num_kernels=0;break;case 1:g.num_kernels=2;break;case 2:g.idrt.max_entries=0;break;case 3:g.idrt.max_entries=2;break;
   case 4:g.idrt.entry_size=32;break;case 5:g.idrt.entry_size=128;break;case 6:g.idrt.bo=NULL;break;case 7:g.dynamic_state.bo=&other;break;
   case 8:g.curbe.bo=&other;break;case 9:g.dynamic_state.bo_size=0;break;case 10:g.dynamic_state.bo_size=-1;break;case 11:g.curbe.length=0;break;
   case 12:g.sampler.max_entries=1;break;case 13:g.sampler.entry_size=64;break;case 14:g.idrt.offset++;break;case 15:g.kernels[0].kernel_offset++;break;
   case 16:g.curbe.length=1025;break;case 17:g.idrt.offset=4096;break;case 18:g.dynamic_state.bo_size=8192;break;
   case 19:g.idrt.offset=UINT_MAX&~63U;break;case 20:g.curbe.offset=UINT_MAX;break;case 21:g.idrt.offset=4096-32;break;
  }
  unsigned oldmaps=maps;CHECK(!mp2_gen8_gpu_idrt_eligible(&g));CHECK(!mp2_gen8_gpu_idrt_upload(NULL,&g,&batch));CHECK(batch.n==0 && batch.relocs==0 && maps==oldmaps);
  for(unsigned i=0;i<4096;i++)CHECK(storage[i]==0xa5);
 }
 struct i965_gpe_context good;valid(&good,&bo);CHECK(!mp2_gen8_gpu_idrt_upload(NULL,&good,NULL));
 puts("4096-byte-equivalent-descriptors; 22-invalid-layouts-no-commands; four-ordered-postsync-writes-and-final-invalidation-pass");return 0;
}
'''
DIAG_MAIN=r'''
int main(int argc,char **argv){
 if(argc!=3)return 10;char pid[32];snprintf(pid,sizeof(pid),"%lu",(unsigned long)getpid());
 setenv("MP2_I965_DIAG_FILE",argv[2],1);setenv("MP2_I965_DIAG_PID",pid,1);
 unsetenv("MP2_I965_GPU_MBENC_IDRT");unsetenv("MP2_I965_EARLY_MBENC_IDRT");
 int enabled=!strcmp(argv[1],"enabled") || !strcmp(argv[1],"reload") || !strcmp(argv[1],"change") || !strcmp(argv[1],"fork");
 if(enabled || !strcmp(argv[1],"both"))setenv("MP2_I965_GPU_MBENC_IDRT","1",1);
 if(!strcmp(argv[1],"early") || !strcmp(argv[1],"both"))setenv("MP2_I965_EARLY_MBENC_IDRT","1",1);
 if(!strcmp(argv[1],"badpid"))setenv("MP2_I965_DIAG_PID","1",1);
 if(!strcmp(argv[1],"v5")){int fd=open(argv[2],O_RDWR|O_CREAT|O_EXCL,0600);if(fd<0 || ftruncate(fd,1856))return 11;close(fd);}
 mp2_diag_initialize();
 if(!strcmp(argv[1],"both") || !strcmp(argv[1],"badpid") || !strcmp(argv[1],"v5")){
  if(data || mp2_diag_gpu_idrt_enabled())return 12;
  if(strcmp(argv[1],"v5") && access(argv[2],F_OK)==0)return 13;
  return 0;
 }
 if(!data || data->version!=6 || data->phases!=26 || sizeof(*data)!=1888 || data->gpu_enabled!=(uint64_t)enabled || offsetof(struct mp2_data,gpu_enabled)!=1856)return 14;
 if(mp2_diag_gpu_idrt_enabled()!=enabled)return 15;
 errno=E2BIG;mp2_diag_gpu_idrt_event(0);mp2_diag_gpu_idrt_event(1);mp2_diag_gpu_idrt_event(2);mp2_diag_gpu_idrt_event(99);
 if(errno!=E2BIG || data->gpu_preparations!=(uint64_t)enabled || data->gpu_command_uploads!=(uint64_t)enabled || data->gpu_fallbacks!=(uint64_t)enabled)return 16;
 if(!strcmp(argv[1],"fork")){
  pid_t child=fork();if(child<0)return 17;if(!child){if(mp2_diag_gpu_idrt_enabled())_exit(18);mp2_diag_gpu_idrt_event(0);_exit(0);}
  int status;if(waitpid(child,&status,0)!=child || status || data->gpu_preparations!=1)return 19;
 }
 mp2_diag_finish();if(data)return 20;
 if(!strcmp(argv[1],"reload")){mp2_diag_initialize();if(!data || data->loads!=2 || data->active_loads!=1 || data->gpu_command_uploads!=1)return 21;mp2_diag_finish();}
 if(!strcmp(argv[1],"change")){unsetenv("MP2_I965_GPU_MBENC_IDRT");mp2_diag_initialize();if(data)return 22;}
 return 0;
}
'''

class Candidate(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=Path(ARGS.source_root);cls.ref=Path(ARGS.reference_root);cls.tmp=tempfile.TemporaryDirectory(prefix='mipad2-GPU-IDRT-');cls.temp=Path(cls.tmp.name)
  proof=json.loads(Path(ARGS.receipt).read_text());require(proof['public_base_commit']=='0b648be50cd80e16469c135c76ff61bbd2f2d12b','Wrong public baseline commit')
  for n,h in proof['changed_sources_SHA256'].items():require(hashlib.sha256((cls.root/'src'/n).read_bytes()).hexdigest()==h,'Candidate changed '+n)
  pins={'i965_gpe_utils.c':'95622c7b837a91f8da51463f00860c088c2e9e2918a48b1c6b6f3c7529cadf60','i965_gpe_utils.h':'584c26617ad9f204da39f0210dd6fe420c0cde36d31ff96618c1583b36cf529c','intel_driver.h':'7ab5693626f4a2281760006fb0de98e7e359459c4aff5455cfdb4d1cbb0621ea','i965_structs.h':'20673227d8bd1cb5fca3a4f8e4259a43ab780cef9c02ae0fa95fbb453887ff38','i965_drv_video.h':'539d3209de3aac325c1309ef6949b6d4e2930d9034d5828d583f28d1b1c017ba'}
  cls.original={}
  for n,h in pins.items():
   raw=(cls.ref/'src'/n).read_bytes();require(hashlib.sha256(raw).hexdigest()==h,'Reference changed '+n);cls.original[n]=raw.decode()
  cls.code=(cls.root/'src/i965_gpe_utils.c').read_text();header=cls.original['i965_gpe_utils.h']
  macros=[s for s in cls.original['intel_driver.h'].splitlines() if s.startswith('#define CMD_3D ') or s.startswith('#define CMD_PIPE_CONTROL')]
  macros += [s for s in header.splitlines() if s.startswith(('#define PIPE_CONTROL_FLUSH_','#define MAX_GPE_KERNELS '))]
  structs=block(cls.original['i965_drv_video.h'],'struct i965_kernel {')+';\n'+block(header,'struct i965_gpe_context {')+';\n'+block(header,'struct gpe_pipe_control_parameter {')+';\n'+block(cls.original['i965_structs.h'],'struct gen8_interface_descriptor_data {')+';\n'
  notice=cls.original['i965_gpe_utils.c'][:cls.original['i965_gpe_utils.c'].index('*/')+2]
  golden='#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wsign-compare"\n'+fn(cls.original['i965_gpe_utils.c'],'gen8_gpe_setup_interface_data')+'\n#pragma GCC diagnostic pop\n'
  cls.harness=notice+'\n'+PRE+'\n'+'\n'.join(macros)+'\n'+structs+'\n'+golden+'\n'+fn(cls.code,'gen8_gpe_pipe_control')+'\n'+fn(cls.code,'mp2_gen8_gpu_idrt_eligible')+'\n'+fn(cls.code,'mp2_gen8_gpu_idrt_upload')+'\n'+MAIN
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def packet(self,label,flags=(),negative=False):
  code=self.harness
  if negative:code=code.replace(fn(self.code,'gen8_gpe_pipe_control'),fn(self.original['i965_gpe_utils.c'],'gen8_gpe_pipe_control'))
  p=self.temp/(label+'.c');p.write_text(code);exe=self.temp/label
  q=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-parameter',*flags,str(p),'-o',str(exe)],capture_output=True,text=True);self.assertEqual(q.returncode,0,q.stderr)
  q=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
  if negative:self.assertEqual(q.returncode,3);self.assertIn('batch.words[j+1]==expected',q.stderr)
  else:self.assertEqual(q.returncode,0,q.stderr);self.assertIn('4096-byte-equivalent-descriptors',q.stdout)
 def test_normal_packet_descriptor_bytes(self):self.packet('normal')
 def test_ndebug_packet_checks_stay_enabled(self):self.packet('ndebug',['-DNDEBUG'])
 def test_ubsan_packet_checks(self):self.packet('ubsan',['-fsanitize=undefined','-fno-sanitize-recover=all'])
 def test_original_boolean_mask_is_required_negative(self):self.packet('negative',['-DNDEBUG'],negative=True)
 def test_cpu_implementation_unchanged(self):self.assertEqual(fn(self.code,'gen8_gpe_setup_interface_data'),fn(self.original['i965_gpe_utils.c'],'gen8_gpe_setup_interface_data'))
 def test_no_unordered_store_or_CPU_map_in_GPU_helper(self):
  code=fn(self.code,'mp2_gen8_gpu_idrt_upload');self.assertNotIn('MI_STORE_DATA_IMM',code);self.assertNotIn('dri_bo_map',code);self.assertNotIn('dri_bo_unmap',code)
 def test_context_ownership_and_hook_order(self):
  src=(self.root/'src/i965_avc_encoder.c').read_text();walker=fn(src,'gen9_avc_run_kernel_media_object_walker')
  self.assertLess(walker.index('intel_batchbuffer_start_atomic'),walker.index('mp2_gen8_gpu_idrt_upload'));self.assertLess(walker.index('gpe->mi_store_data_imm'),walker.index('mp2_gen8_gpu_idrt_upload'))
  self.assertLess(walker.index('mp2_gen8_gpu_idrt_upload'),walker.index('gpe->pipeline_setup'));self.assertLess(walker.index('gpe->pipeline_setup'),walker.index('gpe->media_object_walker'));self.assertLess(walker.index('gpe->media_object_walker'),walker.index('intel_batchbuffer_end_atomic'))
  self.assertLess(walker.index('mbenc_gpu_idrt_pending = NULL'),walker.index('mp2_gen8_gpu_idrt_upload'))
  mb=src[src.index('if (avc_state->mbenc_idrt_prepared != gpe_context)'):];mb=mb[:mb.index('mp2_diag_end(MP2_MB_IDRT')]
  for guard in ['!i_frame_dist_in_use','IS_CHERRYVIEW','!encoder_context->fei_enabled','avc_state->mbenc_curbe_set_in_brc_update','mp2_diag_gpu_idrt_enabled()','mp2_gen8_gpu_idrt_eligible(gpe_context)']:self.assertIn(guard,mb)
  self.assertEqual(src.count('avc_state->mbenc_gpu_idrt_pending = NULL;'),2)
 def test_real_PID_scoped_diagnostic_ABI_defaults_and_reload(self):
  src=(self.root/'src/mp2_i965_diag.c').read_text();self.assertEqual(src.count('__attribute__((constructor)) '),1);self.assertEqual(src.count('__attribute__((destructor)) '),1)
  src=src.replace('__attribute__((constructor)) ','').replace('__attribute__((destructor)) ','')
  p=self.temp/'diag.c';p.write_text('#include <stddef.h>\n#include <stdio.h>\n#include <sys/wait.h>\n'+src+'\n'+DIAG_MAIN);exe=self.temp/'diag'
  q=subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-DNDEBUG','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(self.root/'src'),str(p),'-o',str(exe)],capture_output=True,text=True);self.assertEqual(q.returncode,0,q.stderr)
  for mode in ['default','enabled','early','both','badpid','v5','reload','change','fork']:
   with self.subTest(mode=mode):
    q=subprocess.run([str(exe),mode,str(self.temp/(mode+'.bin'))],capture_output=True,text=True,timeout=15);self.assertEqual(q.returncode,0,q.stderr+' exit='+str(q.returncode))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',required=True);p.add_argument('--reference-root',required=True);p.add_argument('--receipt',required=True);ARGS=p.parse_args()
 raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Candidate)).wasSuccessful() else 1)
