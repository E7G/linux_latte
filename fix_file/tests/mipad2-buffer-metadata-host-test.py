#!/usr/bin/env python3
"""Actual metadata wrappers/helpers with VB2, locks and device stubs.

No hardware, DMA, real queue/IRQ locking, full private-ioctl/compat or 3A proof.
"""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(__file__).resolve().parents[2]
if not (r/'drivers').exists():r=Path('/root/linux_latte-6.14-integrated')
s=(r/'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text()
h=(r/'drivers/staging/media/atomisp/include/linux/atomisp.h').read_text()
fh=(r/'drivers/staging/media/atomisp/pci/atomisp_fops.h').read_text()

def fn(text,name):
    m=re.search(r'(?:static\s+)?(?:inline\s+)?(?:int|struct atomisp_fh \*)\s*'+name+r'\([^;{}]*\)\s*\{',text);assert m,name
    depth=1;end=m.end()
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[m.start():end]+'\n'

api=h[h.index('/* Buffer metadata layout'):h.index('/* Custom format for RAW capture')]
types=fh[fh.index('struct atomisp_metadata_record'):fh.index('/*\n * Memory help')]
functions=''.join(fn(s,n) for n in ['atomisp_qbuf_wrapper','atomisp_dqbuf_wrapper','atomisp_set_buffer_metadata_mode','atomisp_get_frame_metadata'])
base=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <linux/videodev2.h>
typedef uint32_t u32;
typedef struct { int held; } spinlock_t;
struct mutex { int held; };
struct v4l2_fh { unsigned id; };
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define spin_lock_irqsave(p,f) do { (f)=0; assert(!(p)->held); (p)->held=1; } while(0)
#define spin_unlock_irqrestore(p,f) do { assert((p)->held && !(f)); (p)->held=0; } while(0)
#define ATOMISP_BUFFER_HAS_PER_FRAME_SETTING 0x80000000U
'''
model=r'''
struct vb2_buffer { unsigned index; };
struct ia_css_frame { struct vb2_buffer vb; unsigned exp_id; };
struct vb2_queue { void *owner; unsigned count; bool busy; };
struct atomisp_video_pipe { struct vb2_queue vb_queue; struct mutex vb_queue_mutex;
 unsigned frame_request_config_id[VIDEO_MAX_FRAME],frame_config_id[VIDEO_MAX_FRAME];
 struct ia_css_frame frames[VIDEO_MAX_FRAME]; };
struct video_device { struct vb2_queue *queue; struct atomisp_video_pipe *pipe; };
struct file { struct video_device *vdev; void *private_data; };
static int q_error,dq_error,q_calls,dq_calls;
static bool expect_no_mutation;
static unsigned expected_config;
static struct v4l2_buffer returned;
static struct video_device *video_devdata(struct file *f) { return f->vdev; }
static struct atomisp_video_pipe *atomisp_to_video_pipe(struct video_device *v) { return v->pipe; }
static unsigned vb2_get_num_buffers(struct vb2_queue *q) { return q->count; }
static struct vb2_buffer *vb2_get_buffer(struct vb2_queue *q,unsigned i) {
 struct atomisp_video_pipe *p=container_of(q,struct atomisp_video_pipe,vb_queue);
 assert(i<q->count);return &p->frames[i].vb;
}
static struct ia_css_frame *vb_to_frame(struct vb2_buffer *b) { return container_of(b,struct ia_css_frame,vb); }
static bool vb2_is_busy(struct vb2_queue *q) { return q->busy; }
static bool mutex_trylock(struct mutex *m) { if(m->held)return false;m->held=1;return true; }
static void mutex_unlock(struct mutex *m) { assert(m->held);m->held=0; }
static bool vb2_queue_is_busy(struct vb2_queue*q,struct file*f) { return q->owner && q->owner!=f->private_data; }
static int vb2_ioctl_qbuf(struct file *f,void *owner,struct v4l2_buffer *b) {
 (void)owner;q_calls++;
 if(f->vdev->queue->owner && f->vdev->queue->owner!=f->private_data) {
  if(expect_no_mutation)assert(f->vdev->pipe->frame_request_config_id[b->index]==expected_config);
  return -EBUSY;
 }
 return q_error;
}
static int vb2_ioctl_dqbuf(struct file *f,void *owner,struct v4l2_buffer *b) {
 (void)owner;dq_calls++;assert(f->vdev->queue->owner==f->private_data);
 if(dq_error)return dq_error;
 *b=returned;return 0;
}
'''
cases=r'''
int main(void) {
 _Static_assert(sizeof(struct atomisp_frame_metadata)==32,"metadata ABI size");
 _Static_assert(offsetof(struct atomisp_frame_metadata,timestamp_us)==8,"timestamp ABI offset");
 _Static_assert(offsetof(struct atomisp_fh,fh)==0,"generic fh release base");
 _Static_assert(_IOC_SIZE(ATOMISP_IOC_G_FRAME_METADATA)==32,"ioctl ABI size");
 _Static_assert(_IOC_NR(ATOMISP_IOC_S_BUFFER_METADATA_MODE)==BASE_VIDIOC_PRIVATE+50,"mode number");
 _Static_assert(_IOC_NR(ATOMISP_IOC_G_FRAME_METADATA)==BASE_VIDIOC_PRIVATE+51,"metadata number");
 unsigned cases=0;
 for(unsigned mode=0;mode<=2;mode++)for(unsigned exp=0;exp<=250;exp++)for(unsigned error=0;error<2;error++) {
  struct atomisp_fh a={0},b={0};struct atomisp_video_pipe pipe={0};
  struct video_device v={.queue=&pipe.vb_queue,.pipe=&pipe};
  struct file f={.vdev=&v,.private_data=&a.fh},other={.vdev=&v,.private_data=&b.fh};
  assert(atomisp_set_buffer_metadata_mode(&f,mode)==0 && a.metadata_mode==mode && b.metadata_mode==0);
  pipe.vb_queue=(struct vb2_queue){.owner=&a.fh,.count=8,.busy=true};
  returned=(struct v4l2_buffer){.index=exp%8,.sequence=exp+1000,.timestamp={.tv_sec=3,.tv_usec=123+exp},.flags=error?V4L2_BUF_FLAG_ERROR:0};
  pipe.frames[returned.index].exp_id=exp;pipe.frame_config_id[returned.index]=0x123456+exp;
  struct v4l2_buffer buf={0};
  assert(!atomisp_dqbuf_wrapper(&f,NULL,&buf));
  unsigned id=error?0:exp;
  assert(buf.reserved==(mode==0?0:mode==1?id:id<<16));
  assert(buf.reserved2==(mode?pipe.frame_config_id[buf.index]:0));
  struct atomisp_frame_metadata metadata={.index=buf.index,.sequence=buf.sequence,
    .timestamp_us=(uint64_t)buf.timestamp.tv_sec*1000000+buf.timestamp.tv_usec};
  struct atomisp_frame_metadata key=metadata;
  assert(!atomisp_get_frame_metadata(&f,&metadata));
  assert(metadata.exp_id==id && metadata.isp_config_id==pipe.frame_config_id[buf.index]);
  assert(metadata.flags==returned.flags && metadata.reserved==0);
  assert(atomisp_get_frame_metadata(&other,&key)==-EAGAIN); // per-FH isolation
  metadata=key;metadata.sequence++;assert(atomisp_get_frame_metadata(&f,&metadata)==-EAGAIN);
  metadata=key;metadata.timestamp_us++;assert(atomisp_get_frame_metadata(&f,&metadata)==-EAGAIN);
  metadata.index=VIDEO_MAX_FRAME;assert(atomisp_get_frame_metadata(&f,&metadata)==-EINVAL);
  assert(atomisp_set_buffer_metadata_mode(&f,0)==-EBUSY && a.metadata_mode==mode);
  pipe.vb_queue.busy=false;pipe.vb_queue_mutex.held=1;
  assert(atomisp_set_buffer_metadata_mode(&f,0)==-EBUSY && pipe.vb_queue_mutex.held==1);
  pipe.vb_queue_mutex.held=0;
  assert(atomisp_set_buffer_metadata_mode(&f,3)==-EINVAL && a.metadata_mode==mode);
  assert(atomisp_set_buffer_metadata_mode(&f,UINT32_MAX)==-EINVAL && a.metadata_mode==mode);
  pipe.frame_request_config_id[buf.index]=777;expected_config=777;expect_no_mutation=true;
  struct v4l2_buffer q={.index=buf.index,.reserved2=ATOMISP_BUFFER_HAS_PER_FRAME_SETTING|33};
  int calls=q_calls;
  assert(atomisp_qbuf_wrapper(&other,NULL,&q)==-EBUSY && q_calls==calls);
  assert(pipe.frame_request_config_id[buf.index]==777);
  q_error=-EINVAL;
  assert(atomisp_qbuf_wrapper(&f,NULL,&q)==-EINVAL && pipe.frame_request_config_id[buf.index]==777);
  metadata=key;assert(!atomisp_get_frame_metadata(&f,&metadata)); // failed QBUF retains record
  q_error=0;
  assert(!atomisp_qbuf_wrapper(&f,NULL,&q));
  assert(pipe.frame_request_config_id[buf.index]==(mode?33U:0U));
  metadata=key;assert(atomisp_get_frame_metadata(&f,&metadata)==-EAGAIN);
  q.index=VIDEO_MAX_FRAME;calls=q_calls;assert(atomisp_qbuf_wrapper(&f,NULL,&q)==-EINVAL && q_calls==calls);
  q.index=8;assert(atomisp_qbuf_wrapper(&f,NULL,&q)==-EINVAL && q_calls==calls);
  for(unsigned i=0;i<3;i++) {
   int errors[]={-EAGAIN,-EIO,-EINVAL};dq_error=errors[i];
   memset(&buf,0x5a,sizeof(buf));struct v4l2_buffer saved=buf;
   assert(atomisp_dqbuf_wrapper(&f,NULL,&buf)==errors[i] && !memcmp(&saved,&buf,sizeof(buf)));
  }
  dq_error=0;cases++;
 }
 printf("PASS %u source-extracted per-FH metadata/legacy/owner/rollback/error cases, ABI32bytes; stub VB2/locks\n",cases);
}
'''
negative=os.environ.get('MIPAD2_METADATA_NEGATIVE')
if negative=='standard':
    functions=functions.replace('if (afh->metadata_mode != ATOMISP_BUFFER_METADATA_STANDARD) {','if (1) {')
elif negative=='owner':
    functions=functions.replace('\tif (vb2_queue_is_busy(vdev->queue, file))\n\t\treturn -EBUSY;','')
elif negative=='rollback':
    functions=functions.replace('pipe->frame_request_config_id[buf->index] = old_config;','(void)old_config;')
elif negative=='correlation':
    functions=functions.replace('!record->valid || record->frame.sequence != metadata->sequence ||\n\t    record->frame.timestamp_us != metadata->timestamp_us','!record->valid')
# Bindings are compiled in the real kernel; check dispatch hasn't been omitted.
assert 'return atomisp_set_buffer_metadata_mode(file, *(u32 *)arg);' in s
assert 'return atomisp_get_frame_metadata(file, arg);' in s
with tempfile.TemporaryDirectory(prefix='mipad2-metadata-') as temp:
    p=Path(temp);c=p/'test.c';c.write_text(base+api+types+model+functions+cases)
    subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
