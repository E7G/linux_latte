"""Bounded unmodified streaming compliance; whole-device sampled restoration."""
from pathlib import Path
import json,subprocess,time
src=Path('/var/tmp/run_r17_compliance_remote.py').read_text()
exec(src[:src.index('names={')])
assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
folder=BASE/'diagnostics/whole-compliance';assert not folder.exists();folder.mkdir()
names={p.name:(p/'name').read_text().strip() for p in Path('/sys/class/video4linux').glob('v4l-subdev*')}
original=[]
for index,prefix in [(0,'ov5693 '),(1,'t4ka3 ')]:
 node='/dev/'+next(n for n,v in names.items() if v.startswith(prefix))
 original.append(dict(input=index,node=node,shape=shape(node),controls=controls(node,index)))
initial=run(['v4l2-ctl','-d','/dev/video0','--get-input','--get-fmt-video','--get-parm']);assert initial['code']==0
initial_input=int(re.search(r'Video input\s*:\s*(\d+)',initial['stdout']).group(1))
width,height=map(int,re.search(r'Width/Height\s*:\s*(\d+)/(\d+)',initial['stdout']).groups())
fourcc=re.search(r"Pixel Format\s*:\s*'(.{4})'",initial['stdout']).group(1)
report=dict(kernel=BASE.name,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),original=original,initial_video=initial,cases=[],
 scope='unmodified v4l2-compliance --streaming60, starting inputs0 and1; BOTH sensors and video sampled before entire tool and restored per case; no all-format/interval/DMABUF/color/3A claim')
before=run(['dmesg'])['stdout']
def restore():
 result=dict(input=run(['v4l2-ctl','-d','/dev/video0',f'--set-input={initial_input}']),
  video_format=run(['v4l2-ctl','-d','/dev/video0',f'--set-fmt-video=width={width},height={height},pixelformat={fourcc}']),sensors=[])
 for state in original:
  node=state['node'];s=state['shape'];errs=[]
  if s['crop'] is not None:
   x,y,w,h=s['crop'];p=run(['v4l2-ctl','-d',node,f'--set-subdev-selection=pad=0,target=crop,left={x},top={y},width={w},height={h}'])
   if p['code']:errs.append(p)
  p=run(['v4l2-ctl','-d',node,f"--set-subdev-fmt=pad=0,width={s['width']},height={s['height']},code={s['code']}"])
  if p['code']:errs.append(p)
  for cid,value in state['controls'].items():
   try:ctl(node,int(cid),value);assert ctl(node,int(cid))==value
   except Exception as e:errs.append(dict(control=cid,error=repr(e)))
  result['sensors'].append(dict(input=state['input'],shape=shape(node),controls=controls(node,state['input']),errors=errs))
 result['final_video']=run(['v4l2-ctl','-d','/dev/video0','--get-input','--get-fmt-video','--get-parm'])
 result['matched']=result['input']['code']==0 and result['video_format']['code']==0 and result['final_video']==initial and all(
  not a['errors'] and a['shape']==b['shape'] and a['controls']==b['controls'] for a,b in zip(result['sensors'],original))
 return result
try:
 for index in [0,1]:
  assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
  case=dict(starting_input=index);report['cases'].append(case)
  try:
   case['set_input']=run(['v4l2-ctl','-d','/dev/video0',f'--set-input={index}']);assert case['set_input']['code']==0
   case['set_fmt']=run(['v4l2-ctl','-d','/dev/video0','--set-fmt-video=width=1280,height=720,pixelformat=YU12']);assert case['set_fmt']['code']==0
   case['set_parm']=run(['v4l2-ctl','-d','/dev/video0','--set-parm=30']);assert case['set_parm']['code']==0
   start=time.monotonic()
   try:case['compliance']=run(['v4l2-compliance','-d','/dev/video0','--streaming=60','--no-progress'],timeout=180)
   except subprocess.TimeoutExpired as e:
    decode=lambda v:v.decode(errors='replace') if isinstance(v,bytes) else (v or '')
    case['compliance']=dict(code=124,stdout=decode(e.stdout),stderr=decode(e.stderr),bounded_timeout=True)
   case['elapsed_seconds']=time.monotonic()-start
  finally:
   assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1,'Unknown capture survives; no overlapping restore'
   case['restoration']=restore()
  assert case['restoration']['matched'],'Whole-tool sampled restoration mismatch'
  print('starting_input',index,'compliance exit',case['compliance']['code'],'BOTH sensors/video restored',flush=True)
finally:
 after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(before):] if after.startswith(before) else after
 (BASE/'r17-whole-compliance.json').write_text(json.dumps(report,indent=2)+'\n')
assert len(report['cases'])==2 and all(c['compliance']['code']==0 and c['restoration']['matched'] for c in report['cases']), 'Unmodified compliance failed; retain original report'
