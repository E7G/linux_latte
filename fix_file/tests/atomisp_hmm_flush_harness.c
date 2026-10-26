/* SPDX-License-Identifier: GPL-2.0 */
/* Synthetic HMM contract harness. Production function bodies are inserted
 * verbatim by the runner. No real device, cache operation or camera payload. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAGE_SHIFT 4
#define PAGE_SIZE (1U << PAGE_SHIFT)
#define HMM_BO_VMAPED 1
#define HMM_BO_VMAPED_CACHED 2
typedef unsigned int ia_css_ptr;
struct hmm_buffer_object {
 unsigned int start,status;
 void *vmap_addr;
 unsigned char *pages[8];
};
static unsigned char arena[128];
static struct hmm_buffer_object object;
static int bo_device, atomisp_dev;
static unsigned int copies,flushes,flushed_bytes,maps,unmaps,kmaps,kunmaps;
static bool fail_map,fail_check;
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"check failed line %d: %s\n",__LINE__,#c); exit(92); } } while (0)
#define dev_warn(dev,...) ((void)(dev))
#define dev_err(dev,...) ((void)(dev))
static struct hmm_buffer_object *hmm_bo_device_search_in_range(int *device,ia_css_ptr ptr)
{ CHECK(device==&bo_device);return ptr>=object.start && ptr<object.start+sizeof arena?&object:NULL; }
static int hmm_check_bo(struct hmm_buffer_object *bo,ia_css_ptr ptr)
{ (void)ptr;return !bo || fail_check?-EINVAL:0; }
static void *hmm_bo_vmap(struct hmm_buffer_object *bo,bool cached)
{ CHECK(bo==&object && cached);maps++;return fail_map?NULL:arena; }
static void hmm_bo_vunmap(struct hmm_buffer_object *bo)
{ CHECK(bo==&object);unmaps++; }
static void *kmap_local_page(unsigned char *page) { kmaps++;return page; }
static void kunmap_local(void *ptr) { CHECK(ptr>= (void *)arena && ptr<(void *)(arena+sizeof arena));kunmaps++; }
static void clflush_cache_range(void *ptr,unsigned int bytes)
{ CHECK(ptr>= (void *)arena && ptr<=(void *)(arena+sizeof arena));CHECK((unsigned char *)ptr+bytes<=arena+sizeof arena);flushes++;flushed_bytes+=bytes; }
static void *tracked_memcpy(void *dst,const void *src,size_t bytes)
{ if (!dst) { if (bytes) exit(91);return NULL; } copies++;return memcpy(dst,src,bytes); }
#define memcpy tracked_memcpy
/* INSERT_PRODUCTION_FUNCTIONS */
#undef memcpy
int main(int argc,char **argv)
{
 CHECK(argc==2);int which=atoi(argv[1]);CHECK(which>=0 && which<=18);
 object.start=0x1000;object.vmap_addr=arena;
 for (unsigned int i=0;i<sizeof arena;i++) arena[i]=(unsigned char)(i*7+3);
 for (unsigned int i=0;i<8;i++)object.pages[i]=arena+i*PAGE_SIZE;
 unsigned char original[sizeof arena];memcpy(original,arena,sizeof arena);
 unsigned char output[32];memset(output,0,sizeof output);
 if (which>=16) {
  if (which==17)fail_check=true;
  int ret=which==18?hmm_load(object.start+3,NULL,32):hmm_flush(which==16?1:object.start+3,32);
  CHECK(ret==-EINVAL && !copies && !flushes && !maps && !unmaps && !kmaps && !kunmaps);
 } else {
  unsigned int mode=(unsigned int)which%4;
  bool load=((unsigned int)which/4)%2;
  unsigned int bytes=which>=8?0:32;
  if (mode==0)object.status=HMM_BO_VMAPED;
  if (mode==1)object.status=HMM_BO_VMAPED_CACHED;
  fail_map=mode==3;
  int ret=load?hmm_load(object.start+3,output,bytes):hmm_flush(object.start+3,bytes);
  CHECK(!ret && !memcmp(arena,original,sizeof arena));
  if(load)CHECK(!memcmp(output,arena+3,bytes));
  CHECK(copies==(load?(mode==3?(bytes?3:0):1):0));
  CHECK(maps==(mode>=2?1:0));CHECK(unmaps==(mode==2?1:0));
  CHECK(kmaps==(mode==3 && bytes?3:0));CHECK(kunmaps==kmaps);
  CHECK(flushes==(mode==0?0:mode==3?(bytes?3:0):1));
  CHECK(flushed_bytes==(mode==0?0:bytes));
 }
 puts("PASS");return 0;
}
