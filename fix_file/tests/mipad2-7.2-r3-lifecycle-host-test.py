# SPDX-License-Identifier: GPL-2.0
"""Exercise the actual C probe against synthetic syscalls, never real video IO."""
import argparse
from pathlib import Path
import subprocess,tempfile,os,json,hashlib
w=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path)
out=parser.parse_args().output
if out is not None and out.exists():raise RuntimeError('Existing fixture regression receipt')
source=w/'mipad2-7.2-r3-lifecycle-device-test.c'
shim=r'''
#define main actual_probe_main
#define open fake_open
#define ioctl fake_ioctl
#define mmap fake_mmap
#define munmap fake_munmap
#define poll fake_poll
#define close fake_close
#define uname fake_uname
#define fdopen fake_fdopen
#include "PROBE_SOURCE"
#undef main
#include <stdarg.h>
static const char *scenario;
static int owner = -1, nextfd = 10, phase = -1, frame, owner_opens;
static bool queued[4], streaming;
static int is(const char *s) { return strcmp(scenario, s) == 0; }
static int bad(int error) { errno = error; return -1; }
int fake_open(const char *path, int flags, ...) {
 (void)flags;
 return strcmp(path, "/dev/video0") ? 900 : nextfd++;
}
int fake_uname(struct utsname *u) {
 memset(u,0,sizeof(*u));
 strcpy(u->release,is("wrong-release") ? "6.14.0-fixture" : "7.2.0-mipad2-integrated-r3");
 return 0;
}
void *fake_mmap(void *p, size_t n, int prot, int flags, int fd, off_t offset) {
 (void)p;(void)n;(void)prot;(void)flags;(void)fd;(void)offset;
 return calloc(1,1);
}
int fake_munmap(void *p,size_t n) { (void)n;free(p);return 0; }
int fake_close(int fd) {
 if (fd==owner) { owner=-1;streaming=false; }
 else if (fd!=900 && is("observer-close-releases-owner")) owner=-1;
 return 0;
}
FILE *fake_fdopen(int fd,const char *mode) { (void)fd;(void)mode;return tmpfile(); }
int fake_poll(struct pollfd *p,nfds_t n,int timeout) {
 (void)n;(void)timeout;
 if (is("poll-timeout") && frame==17) return 0;
 p->revents=POLLIN;return 1;
}
int fake_ioctl(int fd,unsigned long op,...) {
 va_list ap;va_start(ap,op);void *arg=va_arg(ap,void *);va_end(ap);
 if (op==VIDIOC_QUERYCAP) {
  struct v4l2_capability *c=arg;strcpy((char *)c->driver,is("wrong-driver")?"uvcvideo":"atomisp");return 0;
 }
 if (op==VIDIOC_G_INPUT) { *(unsigned *)arg=0;return 0; }
 if (op==VIDIOC_G_FMT) {
  struct v4l2_format *f=arg;
  f->fmt.pix.width=1920;f->fmt.pix.height=1080;f->fmt.pix.pixelformat=V4L2_PIX_FMT_NV12;
  f->fmt.pix.sizeimage=3112960;f->fmt.pix.bytesperline=1920;f->fmt.pix.field=V4L2_FIELD_NONE;
  if (is("shape-after-stop") && phase>=0 && !streaming) f->fmt.pix.width-=2;
  return 0;
 }
 if (op==VIDIOC_REQBUFS) {
  struct v4l2_requestbuffers *r=arg;
  if (owner>=0 && fd!=owner) return is("nonowner-allocation-accepted")?0:bad(EBUSY);
  if (!r->count) { owner=-1;memset(queued,0,sizeof(queued));return 0; }
  owner=fd;owner_opens++;r->count=4;return 0;
 }
 if (op==VIDIOC_QUERYBUF) {
  struct v4l2_buffer *b=arg;b->length=3112960;b->m.offset=b->index*3112960;return 0;
 }
 if (fd!=owner) return bad(owner<0?ENODEV:EBUSY);
 if (op==VIDIOC_QBUF) {
  struct v4l2_buffer *b=arg;if (b->index>=4) return bad(EINVAL);queued[b->index]=true;return 0;
 }
 if (op==VIDIOC_STREAMON) {
  for (int i=0;i<4;i++) if (!queued[i]) return bad(EINVAL);
  streaming=true;phase++;frame=0;return 0;
 }
 if (op==VIDIOC_STREAMOFF) {
  if (is("streamoff-failure")) return bad(EIO);
  streaming=false;memset(queued,0,sizeof(queued));return 0;
 }
 if (op==VIDIOC_DQBUF) {
  if (!streaming) return bad(EIO);
  struct v4l2_buffer *b=arg;b->index=(unsigned)frame%4;
  if (!queued[b->index]) return bad(EIO);
  queued[b->index]=false;b->bytesused=3112960;b->sequence=(unsigned)frame;
  uint64_t stamp=1000000+(uint64_t)phase*10000000+(uint64_t)frame*33333;
  if (is("duplicate-sequence") && frame==81) b->sequence--;
  if (is("sequence-gap") && frame>=80) b->sequence++;
  if (is("backward-timestamp") && frame==81) stamp-=66666;
  if (is("payload-underrun") && frame==73) b->bytesused--;
  if (is("buffer-error") && frame==73) b->flags|=V4L2_BUF_FLAG_ERROR;
  if (is("metadata-layout-leak") && frame==73) b->request_fd=17;
  b->timestamp.tv_sec=(long)(stamp/1000000);b->timestamp.tv_usec=(long)(stamp%1000000);
  frame++;return 0;
 }
 return bad(EINVAL);
}
int main(int argc,char **argv) {
 if (argc!=2) return 99;
 scenario=argv[1];char *args[]={"probe","/dev/video0","0","synthetic-private.csv",NULL};
 int rc=actual_probe_main(4,args);
 if (!rc && owner_opens!=2) return 98;
 return rc;
}
'''
cases={'valid':0,'sequence-gap':0,'wrong-release':2,'wrong-driver':1,'poll-timeout':1,
 'nonowner-allocation-accepted':1,'observer-close-releases-owner':1,'duplicate-sequence':1,
 'backward-timestamp':1,'payload-underrun':1,'buffer-error':1,'metadata-layout-leak':1,
 'streamoff-failure':1,'shape-after-stop':1}
def strict_result_pass(data):
    """Raw-buffer lifecycle/cadence gate; never an encoded-video/optical gate."""
    if not isinstance(data,dict) or data.get('exit')!=0:return False
    phases=data.get('phases')
    if not isinstance(phases,list) or len(phases)!=4:return False
    return all(isinstance(x,dict) and x.get('frames')==120 and
      x.get('observer_busy_checks')==4 and x.get('sequence_discontinuities')==0 and
      x.get('buffer_errors')==0 and 0<x.get('min_interval_us',0)<=x.get('max_interval_us',0)<=50000 and
      119*x['min_interval_us']<=x.get('sum_interval_us',0)<=119*x['max_interval_us'] for x in phases)

with tempfile.TemporaryDirectory(prefix='mipad2-lifecycle-host-') as t:
    root=Path(t);c=root/'shim.c';binary=root/'shim'
    c.write_text(shim.replace('PROBE_SOURCE',str(source)))
    build=subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
      '-fsanitize=address,undefined','-fno-omit-frame-pointer',str(c),'-o',str(binary)],capture_output=True,text=True)
    if build.returncode:raise RuntimeError(build.stderr)
    results=[]
    for name,expected in cases.items():
        p=subprocess.run([str(binary),name],capture_output=True,text=True,timeout=10,
          env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
        if p.returncode!=expected:raise RuntimeError((name,p.returncode,p.stdout,p.stderr))
        if p.stderr:raise RuntimeError((name,p.stderr))
        data=json.loads(p.stdout) if p.stdout.strip() else None
        if strict_result_pass(data)!=(name=='valid'):raise RuntimeError('Strict lifecycle gate differs: '+name)
        if name=='valid':
            if not all(x['frames']==120 and x['observer_busy_checks']==4 and not x['sequence_discontinuities'] for x in data['phases']):raise RuntimeError('Positive oracle incomplete')
        if name=='sequence-gap':
            if not all(x['sequence_discontinuities']==1 for x in data['phases']):raise RuntimeError('Gap counters lost')
        results.append(dict(scenario=name,exit=p.returncode));print(name,'PASS',flush=True)
result=dict(state='actual-c-fixture-synthetic-syscall-oracles-pass',cases=results,
 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),asan_ubsan_enabled=True,
 real_video_device_opened=False,scope='Synthetic probe oracle only, not kernel driver or DMA fence proof; sequence-gap exit0 requires external strict gate')
if out is not None:out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
