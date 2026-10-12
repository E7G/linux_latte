"""R17-only ACTIVE busy and TRY isolation, with both sensor/video restoration."""
from pathlib import Path
import json, subprocess, time, re
source=Path('/var/tmp/run_r17_whole_compliance_remote.py').read_text()
source=source[:source.index('\ntry:\n')].replace('diagnostics/whole-compliance','diagnostics/sensor-geometry')
exec(source)
report['scope']='R17 sensor ACTIVE fmt/crop EBUSY unchanged, effective per-fd TRY crop/fmt while capturing, both inputs/all three metadata layouts; 240 frames per case; no image quality/3A claim'
binary='/var/tmp/mipad2-r17-sensor-geometry-device-test'
try:
    for index in [0,1]:
        node=original[index]['node']
        for mode in [0,1,2]:
            assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
            case=dict(input=index,metadata_mode=mode); report['cases'].append(case)
            try:
                case['input_set']=run(['v4l2-ctl','-d','/dev/video0',f'--set-input={index}'])
                assert case['input_set']['code']==0
                case['format_set']=run(['v4l2-ctl','-d','/dev/video0','--set-fmt-video=width=1280,height=720,pixelformat=YU12'])
                assert case['format_set']['code']==0
                started=time.monotonic()
                try: case['capture']=run([binary,'/dev/video0','30',node,str(mode)],timeout=90)
                except subprocess.TimeoutExpired as e:
                    decode=lambda x:x.decode(errors='replace') if isinstance(x,bytes) else (x or '')
                    case['capture']=dict(code=124,stdout=decode(e.stdout),stderr=decode(e.stderr),bounded_timeout=True)
                case['elapsed_seconds']=time.monotonic()-started
                log=case['capture']['stdout']
                case['frames']=len(re.findall(r' frame=\d+ bytes=',log))
                case['geometry_guard_phases']=log.count('SENSOR_GEOMETRY_GUARD ACTIVE fmt/crop EBUSY unchanged, TRY independent while streaming PASS')
                phases={}
                for phase,sec,usec in re.findall(r'([a-z-]+) frame=\d+ bytes=\d+ timestamp=(\d+)\.(\d+)',log):
                    phases.setdefault(phase,[]).append(int(sec)+int(usec)*1e-6)
                case['measured_fps']={phase:(len(ts)-1)/(ts[-1]-ts[0]) for phase,ts in phases.items() if len(ts)>1}
                case['short_phase_1pct_cadence']=len(case['measured_fps'])==4 and all(abs(v-30)/30<.01 for v in case['measured_fps'].values())
            finally:
                assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1,'Capture survives; do not overlap restoration'
                case['restoration']=restore()
            assert case['restoration']['matched'],'Sampled restoration failed'
            print('input',index,'metadata',mode,'exit',case['capture']['code'],'frames',case['frames'],'guards',case['geometry_guard_phases'],flush=True)
finally:
    after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(before):] if after.startswith(before) else after
    (BASE/'r17-sensor-geometry.json').write_text(json.dumps(report,indent=2)+'\n')
assert len(report['cases'])==6 and all(c['capture']['code']==0 and c['frames']==240 and c['geometry_guard_phases']==4 and c['restoration']['matched'] for c in report['cases']),'Sensor geometry hardware guard failed; report retained'

