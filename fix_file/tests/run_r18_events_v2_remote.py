"""R18-only real per-fd event regression, with complete writable scalar restoration."""
from pathlib import Path
import hashlib,json,subprocess,time
source=Path('/var/tmp/run_r18_whole_compliance_remote.py').read_text()
source=source[:source.index('\ntry:\n')].replace('diagnostics/whole-compliance','diagnostics/control-events-v2')
exec(source)
assert BASE.name=='6.14.0-mipad2-integrated-r18'
report['scope']='Real per-fd sensor exposure events, initial/change/poll/time/sequence/unsubscribe; BOTH sensors/video and all mutable scalar values restored. No stream/AE/image quality claim.'
binary='/var/tmp/mipad2-r18-control-events-v2'
assert Path(binary).is_file()
report['binary_sha256']=hashlib.sha256(Path(binary).read_bytes()).hexdigest()
try:
    for state in original:
        assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
        case=dict(input=state['input'],node=state['node']);report['cases'].append(case)
        try:
            case['probe']=run([binary,state['node']],timeout=30)
        finally:
            case['restoration']=restore()
        assert case['restoration']['matched'],'Event test restoration failed'
        print('sensor',state['input'],'event probe',case['probe']['code'],'full mutable sampled restoration',flush=True)
finally:
    after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(before):] if after.startswith(before) else after
    (BASE/'r18-control-events-v2.json').write_text(json.dumps(report,indent=2)+'\n')
assert len(report['cases'])==2 and all(c['probe']['code']==0 and c['restoration']['matched'] for c in report['cases']),'Event gate failed; terminal report retained'
