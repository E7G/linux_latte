#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exact reset-stop/free/requeue/update helpers; synthetic heap, not hardware."""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,tempfile
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2]))
prototype=False
b=r  # Public regression tests current source only.
out=Path(os.environ.get('MIPAD2_TEST_OUTPUT',tempfile.mkdtemp(prefix='mipad2-reset-params-report-')));out.mkdir(parents=True,exist_ok=True)
rel='drivers/staging/media/atomisp/pci/atomisp_compat_css20.c'
cmd='drivers/staging/media/atomisp/pci/atomisp_cmd.c'
shade='drivers/staging/media/atomisp/pci/sh_css_param_shading.c'
def extract(s,name):
    m=re.search(r'^(?:static )?(?:void|int)\s*\n?'+name+r'\([^;]*?\)\n\{',s,re.M);assert m,name
    i=s.index('{',m.start())+1;depth=1
    while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
    return s[m.start():i]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
typedef uint16_t u16;
typedef uint32_t u32;
#define ATOMISP_INPUT_STREAM_NUM 2
#define IA_CSS_PIPE_ID_NUM 5
#define ATOMISP_METADATA_TYPE_NUM 2
#define ATOMISP_INPUT_STREAM_GENERAL 0
#define IA_CSS_SC_NUM_COLORS 4
#define VIDEO_MAX_FRAME 4
#define IA_CSS_ENTER(...) ((void)0)
#define IA_CSS_LEAVE(...) ((void)0)
#define dev_warn(...) ((void)0)
#define spin_lock_irqsave(l,f) do{(f)=0;assert(!*(l));*(l)=1;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);assert(*(l)==1);*(l)=0;}while(0)
struct list_head{struct list_head *next,*prev;};
static void list_init(struct list_head*h){h->next=h->prev=h;}
static bool list_empty(const struct list_head*h){return h->next==h;}
static void list_add_tail(struct list_head*n,struct list_head*h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;}
static void list_splice_init(struct list_head*a,struct list_head*b){if(!list_empty(a)){a->next->prev=b;a->prev->next=b->next;b->next->prev=a->prev;b->next=a->next;list_init(a);}}
#define list_entry(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
static unsigned list_count(struct list_head*h){unsigned n=0;for(struct list_head*p=h->next;p!=h;p=p->next){assert(++n<100);}return n;}
struct ia_css_shading_table{u32 enable,sensor_width,sensor_height,width,height,fraction_bits;u16*data[4];};
struct heap_param{unsigned value;};
struct atomisp_css_params{struct heap_param *dvs_6axis,*dvs2_coeff,*morph_table;struct ia_css_shading_table*shading_table;struct{unsigned wb_config,shading_table,dvs_6axis_config;}update_flag;unsigned wb_config;};
struct atomisp_css_params_with_list{struct atomisp_css_params params;struct list_head list;};
struct atomisp_device{int mutex;};
struct atomisp_sub_device;
struct atomisp_video_pipe{struct atomisp_sub_device*asd;struct list_head per_frame_params;struct atomisp_css_params_with_list *frame_params[VIDEO_MAX_FRAME];};
struct fake_config{unsigned value;};
struct atomisp_stream_env{struct fake_config pipe_configs[5],pipe_extra_configs[5],stream_config;void *stream;};
struct atomisp_sub_device{
 struct atomisp_device*isp;bool copy_mode;
 struct atomisp_stream_env stream_env[2];
 struct{struct{struct ia_css_shading_table*shading_table;unsigned*wb_config;}config;bool css_update_params_needed,dis_proj_data_valid;struct atomisp_css_params css_param;}params;
 struct list_head s3a_stats_in_css,s3a_stats_ready,s3a_stats,dis_stats_in_css,dis_stats;
 struct list_head metadata_in_css[2],metadata_ready[2],metadata[2];
 int dis_stats_lock;struct atomisp_video_pipe video_out;
};
static unsigned allocated,freed,stops,destroys,handled,consumed;
static void *allocate(size_t n){void*p=calloc(1,n);assert(p);allocated++;return p;}
static void deallocate(void*p){if(p){freed++;free(p);}}
#define kvfree(p) deallocate(p)
#define kfree(p) deallocate(p)
static void ia_css_dvs2_6axis_config_free(struct heap_param*p){deallocate(p);}
static void ia_css_dvs2_coefficients_free(struct heap_param*p){deallocate(p);}
static void ia_css_morph_table_free(struct heap_param*p){deallocate(p);}
static void atomisp_destroy_pipes_stream(struct atomisp_sub_device*a){assert(a->isp->mutex==1);destroys++;}
static void atomisp_init_raw_buffer_bitmap(struct atomisp_sub_device*a){(void)a;}
static void ia_css_stop_sp(void){stops++;}
static void ia_css_pipe_config_defaults(struct fake_config*c){c->value=0;}
static void ia_css_pipe_extra_config_defaults(struct fake_config*c){c->value=0;}
static void ia_css_stream_config_defaults(struct fake_config*c){c->value=0;}
static void atomisp_handle_parameter_and_buffer(struct atomisp_video_pipe*p){assert(p->asd->isp->mutex==1);handled++;}
static void ia_css_stream_set_isp_config(void*stream,void*configuration){
 (void)stream;typeof(((struct atomisp_sub_device*)0)->params.config)*c=configuration;
 assert(c->shading_table&&c->wb_config);unsigned value=*c->wb_config;
 for(unsigned i=0;i<4;i++)value+=c->shading_table->data[i][0];
 consumed=value;
}
'''
main=r'''
static void alloc_params(struct atomisp_css_params*p,unsigned seed){
 p->dvs_6axis=allocate(sizeof(*p->dvs_6axis));p->dvs_6axis->value=seed+1;
 p->dvs2_coeff=allocate(sizeof(*p->dvs2_coeff));p->dvs2_coeff->value=seed+2;
 p->morph_table=allocate(sizeof(*p->morph_table));p->morph_table->value=seed+3;
 p->shading_table=allocate(sizeof(*p->shading_table));p->shading_table->width=1;
 for(unsigned i=0;i<4;i++){p->shading_table->data[i]=allocate(sizeof(u16));p->shading_table->data[i][0]=(u16)(seed+i);}
 p->wb_config=seed;p->update_flag.wb_config=1;p->update_flag.shading_table=1;p->update_flag.dvs_6axis_config=1;
}
static void init(struct atomisp_sub_device*a,struct atomisp_device*i,unsigned queued,unsigned active,unsigned seed){
 memset(a,0,sizeof(*a));a->isp=i;a->video_out.asd=a;
 list_init(&a->s3a_stats_in_css);list_init(&a->s3a_stats_ready);list_init(&a->s3a_stats);list_init(&a->dis_stats_in_css);list_init(&a->dis_stats);
 list_init(&a->video_out.per_frame_params);
 for(unsigned s=0;s<2;s++){list_init(&a->metadata_in_css[s]);list_init(&a->metadata_ready[s]);list_init(&a->metadata[s]);a->stream_env[s].stream_config.value=seed;for(unsigned p=0;p<5;p++)a->stream_env[s].pipe_configs[p].value=a->stream_env[s].pipe_extra_configs[p].value=seed;}
 alloc_params(&a->params.css_param,seed);
 a->params.config.shading_table=a->params.css_param.shading_table;a->params.config.wb_config=&a->params.css_param.wb_config;
 for(unsigned p=0;p<queued+active;p++){struct atomisp_css_params_with_list*n=allocate(sizeof(*n));alloc_params(&n->params,seed+p+1);if(p<queued)list_add_tail(&n->list,&a->video_out.per_frame_params);else a->video_out.frame_params[p-queued]=n;}
}
static void final_active_cleanup(struct atomisp_video_pipe*p){
 for(unsigned i=0;i<VIDEO_MAX_FRAME;i++)if(p->frame_params[i]){atomisp_free_css_parameters(&p->frame_params[i]->params);kvfree(p->frame_params[i]);p->frame_params[i]=NULL;}
}
int main(int argc,char**argv){
 struct atomisp_device isp={.mutex=1};struct atomisp_sub_device a;
 if(argc>1&&!strcmp(argv[1],"probe-uaf")){
  init(&a,&isp,1,1,37);a.params.css_update_params_needed=true;
  atomisp_css_stop(&a,true);
  /* Actual update helper forwards the retained borrowed pointers. */
  atomisp_css_update_isp_params(&a);assert(consumed==37+37+38+39+40);
  atomisp_css_stop_preserve_config(&a);final_active_cleanup(&a.video_out);
  assert(allocated==freed);puts("PASS real-stop/free/update heap lifetime");return 0;
 }
 unsigned failures=0,cases=0;unsigned repetitions[]={0,1,2,8,64};
 for(unsigned seed=1;seed<=8;seed++)for(unsigned mode=0;mode<2;mode++)for(unsigned reps=0;reps<5;reps++)for(unsigned pending=0;pending<2;pending++)for(unsigned q=0;q<=2;q++)for(unsigned active=0;active<=2;active++){
  init(&a,&isp,q,active,seed);a.params.css_update_params_needed=pending;
  struct atomisp_css_params before=a.params.css_param;
  typeof(a.params.config) config=a.params.config;
  unsigned initially_freed=freed;bool ok=true;
  for(unsigned n=0;n<repetitions[reps];n++){
   atomisp_css_stop(&a,true);
   ok=ok&&freed==initially_freed&&!memcmp(&a.params.css_param,&before,sizeof(before))&&!memcmp(&a.params.config,&config,sizeof(config))&&a.params.css_update_params_needed==(bool)pending&&list_count(&a.video_out.per_frame_params)==q;
   for(unsigned i=0;i<active;i++)ok=ok&&a.video_out.frame_params[i]!=NULL;
  }
  /* Recovery's real requeue helper must retain pending requests too. */
  unsigned before_handle=handled;atomisp_recover_params_queue(&a.video_out);
  ok=ok&&handled==before_handle+1&&list_count(&a.video_out.per_frame_params)==q+active;
  for(unsigned i=0;i<VIDEO_MAX_FRAME;i++)ok=ok&&!a.video_out.frame_params[i];
  /* Final normal stop, including modeled failed recovery's owner stop. */
  if(mode)atomisp_css_stop_preserve_config(&a);else atomisp_css_stop(&a,false);
  ok=ok&&list_empty(&a.video_out.per_frame_params)&&!a.params.config.shading_table&&!a.params.config.wb_config&&!a.params.css_param.shading_table&&!a.params.css_param.dvs_6axis&&!a.params.css_param.dvs2_coeff&&!a.params.css_param.morph_table&&!a.params.css_update_params_needed&&!a.dis_stats_lock&&allocated==freed;
  if(mode)ok=ok&&a.stream_env[0].stream_config.value==seed;else ok=ok&&!a.stream_env[0].stream_config.value;
  unsigned at_end=freed;atomisp_css_stop_preserve_config(&a);ok=ok&&freed==at_end&&allocated==freed;
  cases++;if(!ok)failures++;
 }
 printf("{\"cases\":%u,\"failed\":%u,\"allocated\":%u,\"freed\":%u}\n",cases,failures,allocated,freed);
 return 0;
}
'''
reports={}
with tempfile.TemporaryDirectory(prefix='mipad2-reset-params-') as d:
    for label in (['original','candidate'] if prototype else ['current']):
        css=(b/(label+'.c')).read_text() if prototype else (r/rel).read_text()
        cmdsource=(r/cmd).read_text();shadesource=(r/shade).read_text()
        funcs=extract(shadesource,'ia_css_shading_table_free')+'\n'+extract(cmdsource,'atomisp_free_css_parameters')+'\n'+extract(cmdsource,'atomisp_flush_params_queue')+'\n'+extract(cmdsource,'atomisp_recover_params_queue')+'\n'+'\n'.join(extract(css,n) for n in ['atomisp_css_stop_internal','atomisp_css_stop','atomisp_css_stop_preserve_config','atomisp_css_update_isp_params'])
        p=Path(d)/(label+'.c');p.write_text(prefix+funcs+main);exe=Path(d)/label
        command=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie',str(p),'-o',str(exe)]
        q=subprocess.run(command,capture_output=True,text=True);assert q.returncode==0,q.stderr
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1')
        probe=subprocess.run([str(exe),'probe-uaf'],capture_output=True,text=True,env=env)
        log=out/('mipad2-r24-reset-params-'+label+'-asan.log');assert not log.exists();log.write_text(probe.stdout+probe.stderr)
        assert (probe.returncode!=0 and 'heap-use-after-free' in probe.stderr) if label=='original' else (probe.returncode==0 and not probe.stderr),probe.stderr
        q=subprocess.run([str(exe)],capture_output=True,text=True,env=env);assert q.returncode==0 and not q.stderr,q.stderr
        contract=json.loads(q.stdout);assert contract['cases']==1440 and contract['allocated']==contract['freed'],contract
        assert contract['failed']>0 if label=='original' else contract['failed']==0
        report=dict(label=label,source_sha256={rel:hashlib.sha256(css.encode()).hexdigest(),cmd:hashlib.sha256(cmdsource.encode()).hexdigest(),shade:hashlib.sha256(shadesource.encode()).hexdigest()},
            uaf_probe=dict(exit_code=probe.returncode,heap_use_after_free_detected='heap-use-after-free' in probe.stderr),contract=contract,sanitizers=['address','undefined','leak'],
            scope='Exact stop/free/shading-free/pending-flush/recover-queue/config-update functions; actual synthetic malloc/free and explicit lists/CSS/IRQ/sink stubs. No real firmware, DMA fencing, actual vb2 release/reset timing or image quality proof.')
        dest=out/('mipad2-r24-reset-params-'+label+'-host.json');assert not dest.exists();dest.write_text(json.dumps(report,indent=2)+'\n');reports[label]=report
        print(label,json.dumps(dict(uaf=report['uaf_probe'],contract=contract)),flush=True)
print('Exact borrowed-pointer UAF and reset-parameter loss checks complete; canonical/device source unchanged by fixture.')
