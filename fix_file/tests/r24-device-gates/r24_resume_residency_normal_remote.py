"""Separate functional resume from actual SoC low-power residency."""
import json,re,subprocess,time
from pathlib import Path
base=Path('/var/lib/mipad2-kernel/6.14.0-mipad2-integrated-r24')
assert subprocess.check_output(['uname','-r'],text=True).strip()==base.name
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot==json.loads((base/'verified-runtime.json').read_text())['boot_id']
assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
assert subprocess.check_output(['systemctl','is-active','mipad2-test-no-idle.service'],text=True).strip()=='active'
pm=Path('/sys/kernel/debug/pmc_atom')
def snapshot():
    return {'sleep_state':(pm/'sleep_state').read_text(),'dev_state':(pm/'dev_state').read_text(),
            'pss_state':(pm/'pss_state').read_text(),'wakeup_sources':Path('/sys/kernel/debug/wakeup_sources').read_text(),
            'isp_runtime_status':Path('/sys/bus/pci/devices/0000:00:03.0/power/runtime_status').read_text()}
debug={p:p.read_text() for p in [Path('/sys/power/pm_debug_messages'),Path('/sys/power/pm_print_times')] if p.exists()}
before_log=subprocess.check_output(['dmesg','--color=never'],text=True)
report={'boot_id':boot,'kernel':base.name,'debug_before':{str(p):v for p,v in debug.items()},'before':snapshot()}
try:
    # Leave all PM debug flags exactly as found.
    t=time.clock_gettime(time.CLOCK_BOOTTIME)
    p=subprocess.run(['rtcwake','-m','mem','-s','10'],capture_output=True,text=True,timeout=50)
    report['rtc']={'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'elapsed_boottime':time.clock_gettime(time.CLOCK_BOOTTIME)-t}
    time.sleep(3)
    report['after']=snapshot()
    report['boot_unchanged']=boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    def s0i3(s):return int(re.search(r'S0I3 Residency:\s*(\d+)us',s).group(1))
    report['s0i3_delta_us']=s0i3(report['after']['sleep_state'])-s0i3(report['before']['sleep_state'])
    log=subprocess.check_output(['dmesg','--color=never'],text=True)
    report['new_dmesg']=log[len(before_log):] if log.startswith(before_log) else log
    report['functional_resume_passed']=p.returncode==0 and report['boot_unchanged']
    report['s0i3_entered']=report['s0i3_delta_us']>0
finally:
    for p,v in debug.items():p.write_text(v)
    report['debug_restored']=all(p.read_text()==v for p,v in debug.items())
    (base/'diagnostics/r24-resume-residency-normal.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['before','after','new_dmesg','debug_before']},indent=2))
assert report['functional_resume_passed'] and report['debug_restored']
