#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compile actual timing/range callbacks against control stubs; no hardware proof.

Oracle: Xiaomi Android d2afb1de9a761ff01dafdf9efe4736e521ab71f6 micam/t4ka3.h,
SHA256 73f95c13b0a2771efb00f47030e91a42edb6337a33964336eb24f4832acfd032:
minimum coarse integration 1 line, margin 6 lines, 16-bit frame length.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,tempfile


def require(value,message):
    if not value:raise ValueError(message)


def function(source,name):
    match=re.search(r'^static (?:int|void) '+name+r'\([^;]*?\)\n\{',source,re.M)
    require(match is not None,'Function missing: '+name)
    end=source.index('{',match.start())+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[match.start():end]


def evaluate(source):
    names=['NATIVE_HEIGHT','MIN_VBLANK','MAX_VBLANK','LINES_PER_FRAME_30FPS','COARSE_INTEGRATION_TIME_MARGIN']
    if '#define T4KA3_COARSE_INTEGRATION_TIME_MIN' in source:names.append('COARSE_INTEGRATION_TIME_MIN')
    definitions=[]
    for name in names:
        match=re.search(r'^#define T4KA3_'+name+r'\s+[^\n]+',source,re.M)
        require(match is not None,'Definition missing: '+name);definitions.append(match[0])
    registration=re.search(r'ctrls->exposure\s*=\s*v4l2_ctrl_new_std\(hdl,\s*ops,\s*V4L2_CID_EXPOSURE,\s*([^,]+),\s*max,\s*1,\s*max\);',source)
    require(registration is not None,'Exposure registration shape changed; inspect test')
    minimum=registration[1].strip()
    require(re.fullmatch(r'0|T4KA3_COARSE_INTEGRATION_TIME_MIN',minimum) is not None,'Unsupported initial minimum')
    code=r'''
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#define max(a,b) ((a)>(b)?(a):(b))
struct control { int val; };
struct v4l2_mbus_framefmt { unsigned height; };
struct v4l2_subdev_state { struct v4l2_mbus_framefmt fmt; };
struct t4ka3_data {
 struct { int binning; } mode;
 struct { struct control *vblank,*exposure; } ctrls;
};
static int lower,upper,default_exposure;
static int __v4l2_ctrl_modify_range(struct control *ctrl,int low,int high,int step,int def) {
 (void)ctrl;lower=low;upper=high;default_exposure=def;
 return low>=0 && high>=low && step==1 && def>=low && def<=high ? 0 : -ERANGE;
}
static struct v4l2_mbus_framefmt *v4l2_subdev_state_get_format(struct v4l2_subdev_state *s,int pad) {
 (void)pad;return &s->fmt;
}
'''+ '\n'.join(definitions)+'\n'+function(source,'t4ka3_get_vblank_limits')+'\n'+function(source,'t4ka3_update_exposure_range')+r'''
static unsigned cases,failed,min_frame_failures,exposure_min_failures,other_failures;
static void check(int valid,unsigned *kind) { cases++;if(!valid){failed++;(*kind)++;} }
int main(void) {
 struct control blank={0},exposure={0};
 struct t4ka3_data sensor={.ctrls={.vblank=&blank,.exposure=&exposure}};
 struct v4l2_subdev_state state={0};
 check(INITIAL_MINIMUM==1,&exposure_min_failures);
 for(int binning=1;binning<=2;binning++) {
  sensor.mode.binning=binning;
  for(unsigned height=2;height<=T4KA3_NATIVE_HEIGHT/(unsigned)binning;height+=2) {
   int min,max,def;state.fmt.height=height;
   t4ka3_get_vblank_limits(&sensor,&state,&min,&max,&def);
   check(min>=0 && (int)height+min>=7 && (int)height+max<=65535 && min<=def && def<=max,&min_frame_failures);
   int samples[]={min,def,max};
   for(unsigned i=0;i<3;i++) {
    blank.val=samples[i];int ret=t4ka3_update_exposure_range(&sensor,&state.fmt);
    check(lower==1,&exposure_min_failures);
    check(!ret && upper>=1 && upper==(int)height+blank.val-6 && default_exposure==upper,&other_failures);
   }
  }
 }
 printf("{\"cases\":%u,\"failed\":%u,\"minimum_frame_failures\":%u,\"exposure_minimum_failures\":%u,\"other_failures\":%u}\n",cases,failed,min_frame_failures,exposure_min_failures,other_failures);
 return 0;
}
'''
    code=code.replace('INITIAL_MINIMUM',minimum)
    with tempfile.TemporaryDirectory(prefix='mp2-t4-exposure-range-') as directory:
        root=Path(directory);(root/'test.c').write_text(code)
        subprocess.run(['gcc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',str(root/'test.c'),'-o',str(root/'test')],check=True,capture_output=True,text=True)
        result=json.loads(subprocess.check_output([str(root/'test')],text=True))
    result['source_sha256']=hashlib.sha256(source.encode()).hexdigest();return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline-commit',required=True);args=parser.parse_args()
    root=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2]))
    relative='drivers/media/i2c/t4ka3.c';source=(root/relative).read_text()
    baseline=subprocess.check_output(['git','-C',str(root),'show',args.baseline_commit+':'+relative],text=True)
    result=dict(current=evaluate(source),baseline=evaluate(baseline),baseline_commit=args.baseline_commit,
                control_framework_stubbed=True,hardware_test=False,physical_exposure_or_optical_parity_proven=False)
    print(json.dumps(result,indent=2))
    require(result['current']['failed']==0,'Current T4KA3 range contract fails')
    require(result['baseline']['failed']>0,'Baseline did not reproduce the illegal range')


if __name__=='__main__':main()
