/* SPDX-License-Identifier: MIT
 * Isolated owned-BO readback of the actual private driver's GPU IDRT helper.
 * No camera, decoder, encoder, shader dispatch or foreign GEM handles. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include "i965_drv_video.h"
#include "intel_batchbuffer.h"
#include "i965_gpe_utils.h"
#define CHECK(x) do {if(!(x)){fprintf(stderr,"byteproof line%d: %s\n",__LINE__,#x);exit(3);}}while(0)
#define LOAD(name) __typeof__(&name) f_##name=(__typeof__(&name))dlsym(so,#name);CHECK(f_##name)
static unsigned submissions;
static int checked_exec(drm_intel_bo *bo,int used,drm_clip_rect_t *rect,int nr,int dr4,unsigned flag){
 CHECK(flag==I915_EXEC_RENDER);int ret=drm_intel_bo_mrb_exec(bo,used,rect,nr,dr4,flag);CHECK(ret==0);submissions++;return ret;
}
static void setup(struct i965_gpe_context *g,dri_bo *bo,unsigned n){
 memset(g,0,sizeof(*g));g->num_kernels=1;g->idrt.max_entries=1;g->idrt.entry_size=64;g->idrt.offset=1024;
 g->curbe.bo=g->idrt.bo=g->dynamic_state.bo=bo;g->curbe.length=448+32*(n%3);g->dynamic_state.bo_size=4096;
 g->sampler.offset=1088;g->surface_state_binding_table.binding_table_offset=32*(n%7);g->kernels[0].kernel_offset=64*(17+113*n);
}
int main(int argc,char **argv){
 CHECK(argc==2);CHECK(!getenv("MP2_I965_DIAG_FILE") && !getenv("MP2_I965_GPU_MBENC_IDRT"));
 void *so=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!so){fprintf(stderr,"%s\n",dlerror());return 4;}
 LOAD(intel_batchbuffer_new);LOAD(intel_batchbuffer_free);LOAD(intel_batchbuffer_start_atomic);LOAD(intel_batchbuffer_end_atomic);LOAD(intel_batchbuffer_emit_mi_flush);LOAD(intel_batchbuffer_flush);LOAD(mp2_gen8_gpu_idrt_eligible);LOAD(mp2_gen8_gpu_idrt_upload);LOAD(gen8_gpe_setup_interface_data);
 const struct intel_device_info *(*get_info)(int)=(const struct intel_device_info *(*)(int))dlsym(so,"i965_get_device_info");CHECK(get_info);
 int fd=open("/dev/dri/renderD128",O_RDWR|O_CLOEXEC);CHECK(fd>=0);int devid=0;struct drm_i915_getparam gp={.param=I915_PARAM_CHIPSET_ID,.value=&devid};CHECK(ioctl(fd,DRM_IOCTL_I915_GETPARAM,&gp)==0);
 const struct intel_device_info *info=get_info(devid);CHECK(info && IS_CHERRYVIEW(info) && IS_GEN8(info));
 drmVersionPtr v=drmGetVersion(fd);CHECK(v && !strcmp(v->name,"i915"));drmFreeVersion(v);
 struct intel_driver_data intel={0};intel.fd=fd;intel.device_id=devid;intel.device_info=info;intel.bufmgr=drm_intel_bufmgr_gem_init(fd,16384);CHECK(intel.bufmgr);
 struct intel_batchbuffer *batch=f_intel_batchbuffer_new(&intel,I915_EXEC_RENDER,16384);CHECK(batch);batch->run=checked_exec;
 unsigned cases=0;for(unsigned n=0;n<16;n++){
  dri_bo *cpu=drm_intel_bo_alloc(intel.bufmgr,"CPU reference",4096,4096),*gpu=drm_intel_bo_alloc(intel.bufmgr,"owned GPU IDRT",4096,4096);CHECK(cpu && gpu);
  CHECK(drm_intel_bo_map(cpu,1)==0);CHECK(drm_intel_bo_map(gpu,1)==0);memset(cpu->virtual,0xa5,4096);memset(gpu->virtual,0xa5,4096);drm_intel_bo_unmap(cpu);drm_intel_bo_unmap(gpu);
  struct i965_gpe_context a,b;setup(&a,cpu,n);setup(&b,gpu,n);CHECK(f_mp2_gen8_gpu_idrt_eligible(&b));f_gen8_gpe_setup_interface_data(NULL,&a);
  f_intel_batchbuffer_start_atomic(batch,4096);f_intel_batchbuffer_emit_mi_flush(batch);CHECK(f_mp2_gen8_gpu_idrt_upload(NULL,&b,batch)==1);f_intel_batchbuffer_end_atomic(batch);f_intel_batchbuffer_flush(batch);
  CHECK(drm_intel_gem_bo_wait(gpu,5000000000LL)==0);CHECK(drm_intel_bo_map(cpu,0)==0);CHECK(drm_intel_bo_map(gpu,0)==0);
  CHECK(!memcmp(cpu->virtual,gpu->virtual,4096));
  unsigned char *data=gpu->virtual;for(unsigned i=0;i<4096;i++)if(i<1024 || i>=1056)CHECK(data[i]==0xa5);
  drm_intel_bo_unmap(cpu);drm_intel_bo_unmap(gpu);drm_intel_bo_unreference(cpu);drm_intel_bo_unreference(gpu);cases++;
 }
 CHECK(cases==16 && submissions==16);f_intel_batchbuffer_free(batch);drm_intel_bufmgr_destroy(intel.bufmgr);close(fd);CHECK(dlclose(so)==0);
 puts("{\"state\":\"actual-private-GPU-IDRT-helper-owned-BO-readback-pass\",\"cases\":16,\"successful_render_submissions\":16,\"full_4096B_CPU_vs_GPU_matches\":16,\"outside_32B_descriptor_unchanged\":16,\"blocking_completion_waits\":16,\"camera_or_codec_used\":false,\"cache_bypass_or_async_CPU_maps\":false}");return 0;
}
