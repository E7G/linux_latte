"""R17-only idle crop/format extremes, both sensors; no capture or 3A claim."""
from pathlib import Path
import json,subprocess
source=Path('/var/tmp/run_r17_whole_compliance_remote.py').read_text()
source=source[:source.index('\ntry:\n')].replace('diagnostics/whole-compliance','diagnostics/both-crop-edges')
exec(source)
report['scope']='Both sensor ACTIVE idle crop and direct fmt signed/unsigned extremes, bounded even nonzero shapes; sampled video and both sensors restored; no edge image quality or control transaction failure claim'
try:
    for index,(native_w,native_h) in enumerate([(2624,1956),(3280,2464)]):
        node=original[index]['node']
        selected=run(['v4l2-ctl','-d','/dev/video0',f'--set-input={index}']);assert selected['code']==0
        code=shape(node)['code']
        requests=[(native_w,native_h,2,2),(2147483647,2147483647,4294967295,4294967295),
                  (-2147483648,-2147483648,4294967295,4294967295),
                  (native_w-1,native_h-1,1,1),(0,0,4294967295,4294967295)]
        for x,y,w,h in requests:
            assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
            case=dict(input=index,request=[x,y,w,h]);report['cases'].append(case)
            case['set_crop']=run(['v4l2-ctl','-d',node,f'--set-subdev-selection=pad=0,target=crop,left={x},top={y},width={w},height={h}'])
            assert case['set_crop']['code']==0,case
            case['after_crop']=shape(node);x,y,w,h=case['after_crop']['crop']
            assert x>=0 and y>=0 and w>=2 and h>=2 and x+w<=native_w and y+h<=native_h
            assert not(x&1 or y&1 or w&1 or h&1)
            case['set_fmt']=run(['v4l2-ctl','-d',node,f'--set-subdev-fmt=pad=0,width=4294967295,height=4294967295,code={code}'])
            assert case['set_fmt']['code']==0,case
            case['after_fmt']=shape(node)
            assert case['after_fmt']['width']==w and case['after_fmt']['height']==h
finally:
    assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
    report['restoration']=restore()
    after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(before):] if after.startswith(before) else after
    (BASE/'r17-both-crop-edges.json').write_text(json.dumps(report,indent=2)+'\n')
assert report['restoration']['matched'] and len(report['cases'])==10
print('PASS ten idle crop/format extremes on BOTH sensors; full sampled restoration; no stream started.')
