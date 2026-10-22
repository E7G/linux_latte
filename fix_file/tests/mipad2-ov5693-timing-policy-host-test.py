#!/usr/bin/env python3
"""Actual OV timing helpers; board/mode arithmetic, NOT sensor-rate proof."""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(__file__).resolve().parents[2]
if not(r/'drivers').exists():r=Path('/root/linux_latte-6.14-integrated')
s=(r/'drivers/media/i2c/ov5693.c').read_text()
assert 'ov5693->mipad2 = ov5693_has_mipad2_otp(ov5693);' in s
def function(name):
 m=re.search(r'static unsigned int '+name+r'\([^;{}]*\)\s*\{',s);assert m
 n=m.end();depth=1
 while depth:depth+=(s[n]=='{')-(s[n]=='}');n+=1
 return s[m.start():n]+'\n'
helper=function('ov5693_min_vblank');calc=function('__ov5693_calc_vts')
negative=os.environ.get('MIPAD2_TIMING_POLICY_NEGATIVE')
if negative=='floor':
 helper='static unsigned int ov5693_min_vblank(struct ov5693_device *d) { (void)d;return 4; }\n'
elif negative=='default':
 anchor='\tif (ov5693->mipad2)\n\t\ttgt_fps = OV5693_MIPAD2_DEFAULT_FPS;\n\telse\n'
 assert calc.count(anchor)==1;calc=calc.replace(anchor,'')
else:assert not negative
names=['OV5693_FIXED_PPL','OV5693_PIXEL_RATE','OV5693_MIPAD2_PIXEL_RATE','OV5693_TIMING_MIN_VTS',
 'OV5693_INTEGRATION_TIME_MARGIN','OV5693_EXPOSURE_MIN','OV5693_MIPAD2_DEFAULT_FPS',
 'OV5693_MIPAD2_VBLANK_BINNED','OV5693_MIPAD2_VBLANK_UNBINNED']
macros='\n'.join(re.search(r'^#define '+n+r'\s+[^\n]+',s,re.M)[0] for n in names)+'\n'
base=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define max_t(t,a,b) ((t)(a)>(t)(b)?(t)(a):(t)(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define ALIGN(a,n) (((a)+(n)-1)&~((__typeof__(a))(n)-1))
#define ALIGN_DOWN(a,n) ((a)&~((__typeof__(a))(n)-1))
#define rounddown(a,n) ((a)-(a)%(n))
struct ov5693_device { unsigned pixel_rate; bool mipad2; struct {bool binning_x,binning_y;} mode; };
'''
cases=r'''
int main(void) {
 unsigned count=0;
 for(unsigned board=0;board<2;board++)
 for(unsigned bin=0;bin<4;bin++)
 for(unsigned height=2;height<=1956;height+=2) {
  struct ov5693_device d={.pixel_rate=board?160000000:167680000,.mipad2=board,
   .mode={.binning_x=!!(bin&1),.binning_y=!!(bin&2)}};
  unsigned floor=ov5693_min_vblank(&d);
  assert(floor==(board?(bin==3?16u:24u):4u));
  unsigned vts=__ov5693_calc_vts(&d,height);
  assert(vts>=height+floor && !(vts&1) && vts>=9);
  if(board)assert(vts==1984); /* known Android 30fps default on this board */
  else {
   unsigned fps=(167680000u/2688u/height)/30u*30u;
   if(fps<30)fps=30;
   unsigned legacy=(167680000u/2688u/fps)&~1u;
   unsigned lo=height+4;if(lo<9)lo=9;lo=(lo+1)&~1u;
   assert(vts==(legacy>lo?legacy:lo));
  }
  /* Floor is lines, NOT a30/60fps ceiling. At the tested small/binned
   * geometry,120fps remains representable above the chosen guard band. */
  if(board && height<=400)assert(height+floor<160000000u/2688u/120u);
  count++;
 }
 printf("PASS %u actual OV default/guard policy cases including generic parity, board scoping, mixed binning; arithmetic only, no physical FPS claim\n",count);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-timing-policy-') as temp:
 p=Path(temp);(p/'test.c').write_text(base+macros+helper+calc+cases)
 subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
  '-fno-omit-frame-pointer','-no-pie',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
