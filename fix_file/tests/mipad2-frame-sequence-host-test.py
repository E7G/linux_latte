"""Run actual completion/flush/reset code with list, vb2 and IRQ stubs."""
from pathlib import Path
import subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
if not (repo/'drivers').exists(): repo=Path('/root/linux_latte-6.14-integrated')
cmd=(repo/'drivers/staging/media/atomisp/pci/atomisp_cmd.c').read_text()
ioctl=(repo/'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text()
functions=cmd[cmd.index('void atomisp_buffer_done('):cmd.index('\n/* clean out the parameters')]
start=cmd.index('\tif (frame) {',cmd.index('case IA_CSS_BUFFER_TYPE_OUTPUT_FRAME:',cmd.index('void atomisp_buf_done(')))
end=cmd.index('\n\n\t/*',start)
completion=cmd[start:end]
start=ioctl.index('\tspin_lock_irqsave(&pipe->irq_lock, irqflags);\n\tpipe->use_sof_sequence')
end=ioctl.index('\n\n',start)
reset=ioctl[start:end]
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum vb2_buffer_state { VB2_BUF_STATE_DONE, VB2_BUF_STATE_ERROR, VB2_BUF_STATE_QUEUED };
struct atomisp_video_pipe;
struct list { struct ia_css_frame *head; };
struct atomisp_sub_device { uint32_t sequence; };
struct atomisp_device { void *dev; bool valid_sof; };
struct vb2_buffer { struct atomisp_video_pipe *pipe; uint64_t timestamp; unsigned int index,payload; enum vb2_buffer_state state; bool returned; };
struct ia_css_frame { struct { struct vb2_buffer vb2_buf; unsigned int sequence,field; } vb; struct list queue; };
struct atomisp_video_pipe { struct atomisp_sub_device *asd; struct atomisp_device *isp; bool use_sof_sequence; uint32_t sequence; struct { unsigned int field,sizeimage; } pix; int irq_lock; struct list buffers_in_css,activeq,buffers_waiting_for_param; unsigned int frame_request_config_id[32]; };
#define vb_to_pipe(vb) ((vb)->pipe)
#define lockdep_assert_held(lock) assert(*(lock)==1)
#define spin_lock_irqsave(lock,flags) do { (flags)=0; assert(!*(lock)); *(lock)=1; } while(0)
#define spin_unlock_irqrestore(lock,flags) do { (void)(flags); assert(*(lock)); *(lock)=0; } while(0)
#define atomic_read(p) (*(p))
#define dev_warn(dev,...) do { (void)(dev); } while(0)
#define list_for_each_entry_safe(frame,tmp,list,member) for ((frame)=(list)->head,(tmp)=NULL; (frame) && !(tmp); (frame)=NULL)
static void list_del(struct list *l) { (void)l; }
static uint64_t ktime_get_ns(void) { return 42; }
static void vb2_set_plane_payload(struct vb2_buffer *b,int plane,unsigned int size) { assert(!plane); b->payload=size; }
static void vb2_buffer_done(struct vb2_buffer *b,enum vb2_buffer_state state) { assert(!b->returned); b->state=state; b->returned=true; }
static bool atomisp_css_valid_sof(struct atomisp_device *isp) { return isp->valid_sof; }
'''
wrappers='''
static void complete(struct ia_css_frame *frame, bool error) {
    struct atomisp_video_pipe *pipe=frame ? frame->vb.vb2_buf.pipe : NULL;
    unsigned long irqflags;
'''+completion+'''
}
static void reset_stream(struct atomisp_video_pipe *pipe) {
    struct atomisp_device *isp=pipe->isp;
    unsigned long irqflags;
'''+reset+'''
}
'''
tests=r'''
int main(void) {
    struct atomisp_sub_device asd={0};
    struct atomisp_device isp={0};
    struct atomisp_video_pipe p={.asd=&asd,.isp=&isp,.pix={.field=1,.sizeimage=100}};
    struct ia_css_frame f={0}; f.vb.vb2_buf.pipe=&p;
    reset_stream(&p); assert(!p.use_sof_sequence && !p.sequence);
    for (uint32_t i=0;i<100000;i++) {
        f.vb.vb2_buf.returned=false; f.vb.vb2_buf.payload=0;
        bool error=i%9==0;
        complete(&f,error);
        assert(f.vb.sequence==i && p.sequence==i+1);
        assert(f.vb.vb2_buf.state==(error ? VB2_BUF_STATE_ERROR : VB2_BUF_STATE_DONE));
        assert(f.vb.vb2_buf.payload==(error ? 0u : 100u));
    }
    complete(NULL,false); assert(p.sequence==100000);
    for (unsigned int state=0;state<3;state++) {
        struct ia_css_frame flush[3]={0};
        for(unsigned int i=0;i<3;i++) { flush[i].vb.vb2_buf.pipe=&p; flush[i].vb.vb2_buf.index=i; }
        p.buffers_in_css.head=&flush[0]; p.activeq.head=&flush[1]; p.buffers_waiting_for_param.head=&flush[2];
        p.frame_request_config_id[2]=7;
        atomisp_flush_video_pipe(&p,state,true);
        assert(p.sequence==100000 && !p.frame_request_config_id[2]);
        for(unsigned int i=0;i<3;i++) assert(flush[i].vb.vb2_buf.returned && flush[i].vb.sequence==100000);
    }
    p.sequence=UINT32_MAX; f.vb.vb2_buf.returned=false;
    complete(&f,false); assert(f.vb.sequence==UINT32_MAX && !p.sequence);
    reset_stream(&p); f.vb.vb2_buf.returned=false;
    complete(&f,false); assert(!f.vb.sequence && p.sequence==1);
    isp.valid_sof=true; reset_stream(&p); assert(p.use_sof_sequence);
    for(unsigned int i=0;i<10;i++) {
        asd.sequence=i*3; f.vb.vb2_buf.returned=false;
        complete(&f,i%2); assert(f.vb.sequence==i*3 && !p.sequence);
    }
    puts("PASS actual frame completion, error/flush, STREAMON reset, u32 wrap and legacy SOF code; IRQ/vb2/CSS stubs");
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-sequence-test-') as d:
    p=Path(d);(p/'test.c').write_text(prelude+functions+wrappers+tests)
    subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
