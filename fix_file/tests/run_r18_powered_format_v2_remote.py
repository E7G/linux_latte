"""R18-only bounded idle, runtime-active sensor format reset and exact sampled restore."""
from pathlib import Path
import json,os,struct,fcntl,subprocess,time,re
source=Path('/var/tmp/run_r18_whole_compliance_remote.py').read_text()
source=source[:source.index('\ntry:\n')].replace('diagnostics/whole-compliance','diagnostics/powered-format-v2')
exec(source)
assert BASE.name=='6.14.0-mipad2-integrated-r18'
assert Path('/sys/class/dmi/id/product_name').read_text().strip()=='Mipad2'
assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
bound=[p.resolve() for p in Path('/sys/bus/i2c/drivers/t4ka3').iterdir() if p.is_symlink() and (p.resolve()/'power/control').is_file()]
assert len(bound)==1,bound
power=bound[0]/'power';policy=(power/'control').read_text();original_status=(power/'runtime_status').read_text()
assert policy.strip()=='auto','Do not overwrite an already forced-active runtime policy'
node=next(s['node'] for s in original if s['input']==1)
report['scope']='R18 idle T4 held runtime-active, effective width change/HBLANK fixed range+value, unchanged-width repeat; full mutable scalar snapshot and original PM policy restored. No video stream or full I2C rollback proof.'
report['device_power_path']=str(power);report['original_power_policy']=policy;report['original_runtime_status']=original_status
report['initial_t4_shape']=shape(node)

def hblank():
    with open(node,'rb+',buffering=0) as f:
        b=bytearray(struct.pack('II32siiiiIII',0x009e0902,0,b'',0,0,0,0,0,0,0))
        fcntl.ioctl(f,0xc0445624,b,True)
        cid,kind,name,lo,hi,step,default,flags,_,_=struct.unpack('II32siiiiIII',b)
        assert cid==0x009e0902 and kind==1 and flags&4
        return dict(minimum=lo,maximum=hi,step=step,default=default,value=ctl(node,cid),flags=flags)

def wait_status(expected,seconds=5):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if (power/'runtime_status').read_text().strip()==expected:return
        time.sleep(.1)
    raise AssertionError('Runtime state did not become '+expected)

failure=None
try:
    selected=run(['v4l2-ctl','-d','/dev/video0','--set-input=1']);assert selected['code']==0
    # Match the actual GUI failure and controlled R17 baseline, not just a
    # smaller or unrelated source format. All original state is still saved.
    report['gui_mode_prepare']=run(['v4l2-ctl','-d','/dev/video0','--set-fmt-video=width=1920,height=1440,pixelformat=YU12','--set-parm=30'])
    assert report['gui_mode_prepare']['code']==0
    saved=shape(node);report['probe_base_shape']=saved
    assert saved['width']==1936 and saved['height']==1456 and saved['crop']
    alternate=saved['width']-2
    (power/'control').write_text('on\n');wait_status('active')
    for probe_width in [alternate,alternate,saved['width']]:
        assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
        case=dict(requested_width=probe_width,powered_before=(power/'runtime_status').read_text());report['cases'].append(case)
        case['set_fmt']=run(['v4l2-ctl','-d',node,f"--set-subdev-fmt=pad=0,width={probe_width},height={saved['height']},code={saved['code']}"])
        case['after_shape']=shape(node);case['hblank']=hblank()
        case['powered_after']=(power/'runtime_status').read_text()
        assert case['set_fmt']['code']==0,case
        assert case['after_shape']['width']==probe_width and case['after_shape']['height']==saved['height']
        assert case['powered_before'].strip()==case['powered_after'].strip()=='active'
        expected=3440-probe_width
        assert all(case['hblank'][key]==expected for key in ['minimum','maximum','default','value']),case
        print('powered width',probe_width,'S_FMT0 HBLANK',expected,'range/value coherent',flush=True)
except Exception as e:
    failure=repr(e);report['failure']=failure
finally:
    # Restore auto before the geometry restore, so even a failed powered setter
    # does not keep the sensor awake or require an unsupported powered callback.
    (power/'control').write_text(policy)
    report['power_policy_restored']=(power/'control').read_text()==policy
    if original_status.strip()=='suspended':
        try:wait_status('suspended')
        except Exception as e:report['runtime_restore_error']=repr(e)
    report['restoration']=restore()
    report['power_after_restore']=(power/'runtime_status').read_text()
    after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(before):] if after.startswith(before) else after
    (BASE/'r18-powered-format-v2.json').write_text(json.dumps(report,indent=2)+'\n')
assert report['power_policy_restored'] and report['restoration']['matched'] and not report.get('runtime_restore_error')
assert failure is None and len(report['cases'])==3,'Powered format test failed; terminal report retained'
