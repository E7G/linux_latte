"""Unmodified direct subdev compliance, with full sampled idle restoration."""
from pathlib import Path
import json,subprocess,time
source=Path('/var/tmp/run_r18_whole_compliance_remote.py').read_text()
source=source[:source.index('\ntry:\n')].replace('diagnostics/whole-compliance','diagnostics/direct-sensor-compliance')
exec(source)
report['scope']='Unmodified v4l2-compliance -u for both sensor subdevices; no streaming option. BOTH sensor and video sampled restoration; retain failures, not an image/3A test.'
try:
    for state in original:
        case=dict(input=state['input'],node=state['node']);report['cases'].append(case)
        try:
            assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
            case['set_input']=run(['v4l2-ctl','-d','/dev/video0',f"--set-input={state['input']}"]);assert case['set_input']['code']==0
            case['set_fmt']=run(['v4l2-ctl','-d','/dev/video0','--set-fmt-video=width=1280,height=720,pixelformat=YU12']);assert case['set_fmt']['code']==0
            started=time.monotonic()
            try:case['compliance']=run(['v4l2-compliance','-u',state['node'],'--no-progress'],timeout=180)
            except subprocess.TimeoutExpired as e:
                decode=lambda x:x.decode(errors='replace') if isinstance(x,bytes) else (x or '')
                case['compliance']=dict(code=124,stdout=decode(e.stdout),stderr=decode(e.stderr),bounded_timeout=True)
            case['elapsed_seconds']=time.monotonic()-started
        finally:
            assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
            case['restoration']=restore()
        assert case['restoration']['matched'],'Direct sensor compliance restoration failed'
        print('sensor',state['input'],'compliance exit',case['compliance']['code'],'BOTH sensors/video restored',flush=True)
finally:
    after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(before):] if after.startswith(before) else after
    (BASE/'r18-sensor-compliance.json').write_text(json.dumps(report,indent=2)+'\n')
assert len(report['cases'])==2 and all(c['compliance']['code']==0 and c['restoration']['matched'] for c in report['cases']),'Direct sensor compliance failed; original report retained'
