#!/usr/bin/env python3
"""Actual CSS stop/validation code; firmware, queues and IRQs are stubs.

Preservation, pointer cleanup and pre-DMA error gate only, NOT hardware restart.
"""
from pathlib import Path
import subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
css=(repo/'drivers/staging/media/atomisp/pci/atomisp_compat_css20.c').read_text()
css=css[css.index('static void atomisp_css_stop_internal('):css.index('\nvoid atomisp_css_continuous_set_num_raw_frames')]
ioctl=(repo/'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text()
validate=ioctl[ioctl.index('static int atomisp_validate_frame_info('):ioctl.index('\nint atomisp_start_streaming(')]
start=ioctl.index('\tret = atomisp_validate_frame_info(pipe);',ioctl.index('int atomisp_start_streaming('))
guard=ioctl[start:ioctl.index('\n\t/*',start)]
prelude=r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define ATOMISP_INPUT_STREAM_NUM 2
#define IA_CSS_PIPE_ID_NUM 5
#define ATOMISP_METADATA_TYPE_NUM 2
#define VB2_BUF_STATE_QUEUED 7
struct list { unsigned count; };
struct mutex { int depth; };
struct atomisp_device { struct mutex mutex; };
struct fake_config { unsigned value; };
struct atomisp_stream_env { struct fake_config pipe_configs[5],pipe_extra_configs[5],stream_config; };
struct atomisp_video_pipe;
struct atomisp_sub_device {
 struct atomisp_device *isp;
 struct atomisp_stream_env stream_env[2];
 struct { struct {void *shading_table,*other;} config;
     bool css_update_params_needed,dis_proj_data_valid;
     struct {void *shading_table,*other;} css_param; } params;
 struct list s3a_stats_in_css,s3a_stats_ready,s3a_stats,dis_stats_in_css,dis_stats;
 struct list metadata_in_css[2],metadata_ready[2],metadata[2];
 int dis_stats_lock;
 struct {int dummy;} video_out;
};
struct ia_css_frame_info { struct {unsigned width,height;} res;
 unsigned padded_width,format,raw_bit_depth,raw_bayer_order;
 struct {unsigned start_column,start_line;} crop_info; };
struct atomisp_video_pipe { struct atomisp_sub_device *asd;struct ia_css_frame_info frame_info; };
static unsigned destroyed,bitmap,stopped,defaults,flushed,freed,prepared,returned;
static struct ia_css_frame_info output;
static int get_error;
#define lockdep_assert_held(m) assert((m)->depth==1)
#define spin_lock_irqsave(lock,flags) do {(flags)=0;assert(!*(lock));*(lock)=1;}while(0)
#define spin_unlock_irqrestore(lock,flags) do {(void)(flags);assert(*(lock)==1);*(lock)=0;}while(0)
static void atomisp_destroy_pipes_stream(struct atomisp_sub_device *a) {assert(a->isp->mutex.depth==1);destroyed++;}
static void atomisp_init_raw_buffer_bitmap(struct atomisp_sub_device *a) {(void)a;assert(destroyed==1);bitmap++;}
static void ia_css_stop_sp(void) {assert(bitmap==1);stopped++;}
static void ia_css_pipe_config_defaults(struct fake_config *c) {assert(stopped==1);c->value=0;defaults++;}
static void ia_css_pipe_extra_config_defaults(struct fake_config *c) {c->value=0;defaults++;}
static void ia_css_stream_config_defaults(struct fake_config *c) {c->value=0;defaults++;}
static void list_splice_init(struct list *from,struct list *to) {to->count+=from->count;from->count=0;}
static void atomisp_flush_params_queue(void *p) {(void)p;flushed++;}
static void atomisp_free_css_parameters(void *p) {assert(flushed==1);(void)p;freed++;}
static int atomisp_get_css_frame_info(struct atomisp_sub_device *a,struct ia_css_frame_info *info) {
 assert(a->isp->mutex.depth==1);if(get_error)return get_error;*info=output;return 0;
}
static void atomisp_flush_video_pipe(struct atomisp_video_pipe *p,int state,bool reset) {
 assert(p->asd->isp->mutex.depth==1 && state==VB2_BUF_STATE_QUEUED && reset);returned++;
}
"""
wrapper="""
static int prepare(struct atomisp_video_pipe *pipe) {
 int ret;
"""+guard+"""
 prepared++;
out_unlock:
 return ret;
}
"""
cases=r"""
int main(void) {
 struct atomisp_device isp={.mutex={.depth=1}};
 struct atomisp_sub_device asd;
 unsigned count=0;
 for(unsigned cycle=0;cycle<100000;cycle++)for(unsigned mode=0;mode<3;mode++) {
  memset(&asd,0,sizeof(asd));asd.isp=&isp;
  destroyed=bitmap=stopped=defaults=flushed=freed=0;
  for(unsigned i=0;i<2;i++) {
   asd.stream_env[i].stream_config.value=cycle+1;
   for(unsigned j=0;j<5;j++) {asd.stream_env[i].pipe_configs[j].value=cycle+j+1;asd.stream_env[i].pipe_extra_configs[j].value=cycle+j+2;}
   asd.metadata[i].count=1;asd.metadata_ready[i].count=2;asd.metadata_in_css[i].count=3;
  }
  typeof(asd.stream_env) before;memcpy(before,asd.stream_env,sizeof(before));
  asd.params.config.shading_table=&asd;asd.params.config.other=&isp;
  asd.params.css_param.shading_table=&asd;asd.params.css_param.other=&isp;
  asd.params.css_update_params_needed=asd.params.dis_proj_data_valid=true;
  asd.s3a_stats.count=1;asd.s3a_stats_ready.count=2;asd.s3a_stats_in_css.count=3;
  asd.dis_stats.count=1;asd.dis_stats_in_css.count=2;
  if(mode==2)atomisp_css_stop_preserve_config(&asd);else atomisp_css_stop(&asd,mode==1);
  assert(destroyed==1 && stopped==1 && flushed==1 && freed==1 && !asd.dis_stats_lock);
  assert(defaults==(mode==0?22u:0u));
  if(mode)assert(!memcmp(before,asd.stream_env,sizeof(before)));
  else {typeof(asd.stream_env) zero={0};assert(!memcmp(zero,asd.stream_env,sizeof(zero)));}
  if(mode!=1)assert(!asd.params.config.shading_table && !asd.params.config.other && !asd.params.css_update_params_needed);
  else assert(asd.params.config.shading_table==&asd && asd.params.css_update_params_needed);
  assert(!asd.params.css_param.shading_table && !asd.params.css_param.other && !asd.params.dis_proj_data_valid);
  assert(asd.s3a_stats.count==6 && !asd.s3a_stats_ready.count && !asd.s3a_stats_in_css.count);
  assert(asd.dis_stats.count==3 && !asd.dis_stats_in_css.count);
  for(unsigned i=0;i<2;i++)assert(asd.metadata[i].count==6 && !asd.metadata_ready[i].count && !asd.metadata_in_css[i].count);
  count++;
 }
 struct atomisp_video_pipe pipe={.asd=&asd};
 for(unsigned cycle=0;cycle<10000;cycle++) {
  pipe.frame_info=(struct ia_css_frame_info){.res={1280+cycle,720+cycle},.padded_width=1280+cycle,.format=3,.raw_bit_depth=10,.raw_bayer_order=1,.crop_info={2,4}};
  for(unsigned field=0;field<9;field++) {
   output=pipe.frame_info;get_error=0;prepared=returned=0;
   switch(field) {
    case 0:output.res.width++;break;case 1:output.res.height++;break;
    case 2:output.padded_width++;break;case 3:output.format++;break;
    case 4:output.raw_bit_depth++;break;case 5:output.raw_bayer_order++;break;
    case 6:output.crop_info.start_column++;break;case 7:output.crop_info.start_line++;break;
   }
   assert(prepare(&pipe)==(field==8?0:-EINVAL));
   assert(prepared==(field==8) && returned==(field!=8));count++;
  }
  int errors[]={-EINVAL,-ENOMEM,-EIO};
  for(unsigned i=0;i<3;i++) {
   output=pipe.frame_info;get_error=errors[i];prepared=returned=0;
   assert(prepare(&pipe)==errors[i] && returned==1 && !prepared);count++;
  }
 }
 printf("PASS %u actual CSS-stop/layout/error-gate cases; firmware/list/IRQ stubs, NOT hardware restart\n",count);
}
"""
with tempfile.TemporaryDirectory(prefix='mipad2-css-restart-') as d:
 p=Path(d);(p/'test.c').write_text(prelude+css+validate+wrapper+cases)
 subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
