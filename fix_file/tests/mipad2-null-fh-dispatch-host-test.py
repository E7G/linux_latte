#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Actual V4L2 dispatch/VB2 ownership functions plus AtomISP wrappers.

Reuse explicit userspace stubs from the metadata regression. Core allocation,
MMIO/DMA and scheduling are not exercised. Never run these probes on hardware.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,tempfile

def extract(text,name):
    match=re.search(r'^(?:static[ \t]+)?(?:inline[ \t]+)?(?:int|bool|long)[ \t]+'+name+r'\([^;{}]*\)\s*\{',text,re.M)
    assert match,name
    pos=text.index('{',match.start())+1;depth=1
    while depth:
        depth+=(text[pos]=='{')-(text[pos]=='}');pos+=1
    return text[match.start():pos]

def run(root,expect_red=False,baseline_commit=None):
    scaffold=root/'fix_file/tests/mipad2-buffer-metadata-host-test.py'
    text=scaffold.read_text();namespace={'__file__':str(scaffold),'__name__':'metadata_scaffold_only'}
    # Only load its declarations/model strings; do not execute its own compiler.
    exec(compile(text.split("negative=os.environ.get('MIPAD2_METADATA_NEGATIVE')")[0],str(scaffold),'exec'),namespace)
    if baseline_commit:
        assert re.fullmatch(r'[0-9a-f]{40}',baseline_commit)
        old=subprocess.check_output(['git','-C',str(root),'show',baseline_commit+':drivers/staging/media/atomisp/pci/atomisp_ioctl.c'],text=True)
        namespace['s']=old
        namespace['functions']=''.join(namespace['fn'](old,n) for n in ['atomisp_qbuf_wrapper','atomisp_dqbuf_wrapper','atomisp_set_buffer_metadata_mode','atomisp_get_frame_metadata'])
    ioctl_path='drivers/media/v4l2-core/v4l2-ioctl.c'
    vb2_path='drivers/media/common/videobuf2/videobuf2-v4l2.c'
    header_path='include/media/videobuf2-v4l2.h'
    ioctl=(root/ioctl_path).read_text();vb2=(root/vb2_path).read_text();header=(root/header_path).read_text()
    assert re.search(r'ops->vidioc_default\(file,\s*NULL,',ioctl),'Re-audit default callback convention'
    dispatch='\n'.join(extract(ioctl,n) for n in ['v4l_reqbufs','v4l_qbuf','v4l_dqbuf'])
    assert all(re.search(r'ops->'+name+r'\(file,\s*NULL,',dispatch) for name in ['vidioc_reqbufs','vidioc_qbuf','vidioc_dqbuf'])
    core='\n'.join(extract(vb2,n) for n in ['vb2_ioctl_reqbufs','vb2_ioctl_qbuf','vb2_ioctl_dqbuf'])
    model=namespace['model'].split('static int vb2_ioctl_qbuf(')[0]
    if 'static bool vb2_queue_is_busy(' in model:
        model=model.replace(extract(model,'vb2_queue_is_busy'),'')
    model=model.replace('struct video_device {','struct v4l2_device { void *mdev; };\nstruct video_device { struct v4l2_device *v4l2_dev;')
    model=model.replace('struct file {','struct file { int f_flags;')
    model=model.replace('struct atomisp_video_pipe {','struct atomisp_sub_device { struct { int css_param; bool css_update_params_needed; } params; };\nstruct atomisp_video_pipe { struct atomisp_sub_device *asd;')
    stubs=r"""
#include <fcntl.h>
#ifndef VIDIOC_REMOVE_BUFS
#define VIDIOC_REMOVE_BUFS 0xffffffffU
#endif
#define memset_after(p,v,m) ((void)(p))
static int is_valid_ioctl(struct video_device*v,unsigned n){(void)v;(void)n;return 0;}
static int check_fmt(struct file*f,unsigned type){(void)f;return type==V4L2_BUF_TYPE_VIDEO_CAPTURE?0:-EINVAL;}
static int vb2_verify_memory_type(struct vb2_queue*q,unsigned m,unsigned t){(void)q;return m==V4L2_MEMORY_MMAP&&t==V4L2_BUF_TYPE_VIDEO_CAPTURE?0:-EINVAL;}
static void vb2_set_flags_and_caps(struct vb2_queue*q,unsigned m,u32*f,u32*c,void*max){(void)q;(void)m;(void)f;(void)max;*c=0;}
static int vb2_core_reqbufs(struct vb2_queue*q,unsigned m,unsigned f,unsigned*c){(void)m;(void)f;q->count=*c;q->busy=*c!=0;return 0;}
static int vb2_qbuf(struct vb2_queue*q,void*m,struct v4l2_buffer*b){(void)q;(void)m;(void)b;q_calls++;return q_error;}
static int vb2_dqbuf(struct vb2_queue*q,struct v4l2_buffer*b,bool nonblock){(void)q;(void)nonblock;dq_calls++;if(dq_error)return dq_error;*b=returned;return 0;}
struct v4l2_ioctl_ops {
 int (*vidioc_reqbufs)(struct file*,void*,struct v4l2_requestbuffers*);
 int (*vidioc_qbuf)(struct file*,void*,struct v4l2_buffer*);
 int (*vidioc_dqbuf)(struct file*,void*,struct v4l2_buffer*);
};
"""
    init=r"""
int main(int argc,char**argv){
 if(argc!=2)return 99;
 struct atomisp_fh a={0},other={0};struct atomisp_video_pipe pipe={0};struct v4l2_device dev={0};
 struct video_device v={.queue=&pipe.vb_queue,.pipe=&pipe,.v4l2_dev=&dev};
 struct file f={.vdev=&v,.private_data=&a.fh},foreign={.vdev=&v,.private_data=&other.fh};
 struct v4l2_ioctl_ops ops={.vidioc_reqbufs=vb2_ioctl_reqbufs,.vidioc_qbuf=atomisp_qbuf_wrapper,.vidioc_dqbuf=atomisp_dqbuf_wrapper};
 struct v4l2_requestbuffers req={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP,.count=8};
 struct v4l2_buffer b={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE,.memory=V4L2_MEMORY_MMAP,.index=2};
 u32 request_mode=2;
 if(atomisp_vidioc_default(&f,NULL,true,0x7fffffffU,&request_mode)!=-EINVAL||legacy_calls)return 31;
 if(!strcmp(argv[1],"mode")){
  int ret=CALL_MODE;
  return ret||a.metadata_mode!=2||other.metadata_mode!=0;
 }
 if(!strcmp(argv[1],"metadata")){
  a.metadata[2].valid=true;a.metadata[2].frame=(struct atomisp_frame_metadata){.index=2,.sequence=9,.timestamp_us=123,.exp_id=42};
  struct atomisp_frame_metadata result={.index=2,.sequence=9,.timestamp_us=123};
  int ret=CALL_METADATA;
  return ret||result.exp_id!=42;
 }
 if(v4l_reqbufs(&ops,&f,&req)||pipe.vb_queue.owner!=f.private_data)return 11;
 if(!strcmp(argv[1],"qbuf")){
  pipe.frame_request_config_id[2]=777;
  int ret=v4l_qbuf(&ops,&f,&b);
  if(ret||q_calls!=1||pipe.frame_request_config_id[2]!=0)return 12;
  pipe.frame_request_config_id[2]=777;int count=q_calls;
  if(v4l_qbuf(&ops,&foreign,&b)!=-EBUSY||q_calls!=count||pipe.frame_request_config_id[2]!=777)return 13;
  req.count=0;if(v4l_reqbufs(&ops,&f,&req)||pipe.vb_queue.owner)return 14;
  req.count=8;if(v4l_reqbufs(&ops,&foreign,&req)||pipe.vb_queue.owner!=foreign.private_data)return 15;
  return v4l_qbuf(&ops,&foreign,&b)||q_calls!=count+1;
 }
 if(!strcmp(argv[1],"dqbuf")){
  returned=b;returned.sequence=9;returned.timestamp.tv_sec=3;returned.timestamp.tv_usec=123;
  pipe.frames[2].exp_id=42;pipe.frame_config_id[2]=99;
  if(v4l_dqbuf(&ops,&f,&b)||!a.metadata[2].valid||a.metadata[2].frame.exp_id!=42||other.metadata[2].valid)return 21;
  int count=dq_calls;if(v4l_dqbuf(&ops,&foreign,&b)!=-EBUSY||dq_calls!=count)return 22;
  return 0;
 }
 return 98;
}
"""
    driver=namespace['s']
    mode=extract(driver,'atomisp_set_buffer_metadata_mode')
    getter=extract(driver,'atomisp_get_frame_metadata')
    init=init.replace('CALL_MODE','atomisp_vidioc_default(&f,NULL,true,ATOMISP_IOC_S_BUFFER_METADATA_MODE,&request_mode)')
    init=init.replace('CALL_METADATA','atomisp_vidioc_default(&f,NULL,false,ATOMISP_IOC_G_FRAME_METADATA,&result)')
    private=extract(driver,'atomisp_vidioc_default')
    # The complete production dispatcher is unchanged. Only legacy bodies
    # already rejected by its whitelist have inert declarations in this model.
    legacy='static unsigned legacy_calls;\n'
    commands=sorted(set(re.findall(r'case (ATOMISP_[A-Z0-9_]+):',private)) - {'ATOMISP_IOC_S_BUFFER_METADATA_MODE','ATOMISP_IOC_G_FRAME_METADATA'})
    for index,name in enumerate(commands):legacy+='#define '+name+' '+hex(0x1000+index)+'U\n'
    calls=set(re.findall(r'\b(atomisp_[a-z0-9_]+)\(',private)) - {'atomisp_vidioc_default','atomisp_to_video_pipe','atomisp_set_buffer_metadata_mode','atomisp_get_frame_metadata'}
    for name in sorted(calls):legacy+='#define '+name+'(...) ((legacy_calls++),0)\n'
    code=namespace['base']+namespace['api']+namespace['types']+model+stubs+extract(header,'vb2_queue_is_busy')+'\n'+core+'\n'+namespace['functions']+'\n'+legacy+'\n'+private+'\n'+dispatch+'\n'+init
    rows=[]
    with tempfile.TemporaryDirectory(prefix='mipad2-null-fh-') as directory:
        p=Path(directory);(p/'probe.c').write_text(code)
        build=subprocess.run(['cc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(p/'probe.c'),'-o',str(p/'probe')],capture_output=True,text=True)
        assert build.returncode==0,build.stderr
        for label in ['qbuf','dqbuf','mode','metadata']:
            q=subprocess.run([str(p/'probe'),label],capture_output=True,text=True,timeout=20)
            rows.append(dict(case=label,exit_code=q.returncode,passed=q.returncode==0,sanitizer_fault=('runtime error:' in q.stderr or 'AddressSanitizer' in q.stderr)))
    result=dict(state='pass' if all(row['passed'] for row in rows) else 'fail',cases=rows,source_sha256={name:hashlib.sha256(driver.encode() if name=='drivers/staging/media/atomisp/pci/atomisp_ioctl.c' else (root/name).read_bytes()).hexdigest() for name in [ioctl_path,vb2_path,header_path,'drivers/staging/media/atomisp/pci/atomisp_ioctl.c']},baseline_commit=baseline_commit,scope='Actual V4L2 NULL reqbuf/qbuf/dqbuf dispatch, VB2 ownership helpers, AtomISP wrappers and complete AtomISP private dispatcher. Core default NULL callsite inspected; rejected legacy bodies are inert stubs. Allocation/MMIO/DMA/IRQ/locks are synthetic, not physical hardware.')
    print(json.dumps(result,indent=2))
    assert result['state']==('fail' if expect_red else 'pass'),result
    if expect_red:assert all(not row['passed'] for row in rows),rows
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expect-red',action='store_true');parser.add_argument('--baseline-commit');args=parser.parse_args()
    run(Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2])),args.expect_red,args.baseline_commit)
