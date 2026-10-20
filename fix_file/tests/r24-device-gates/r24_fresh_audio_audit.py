"""R4 in-tree DAPM cold-boot and post-s2idle electrical check; silent PCM only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import wave

assert os.geteuid()==0
release='6.14.0-mipad2-integrated-r24'
assert subprocess.check_output(['uname','-r'],text=True).strip()==release
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
selection=json.loads((Path('/var/lib/mipad2-kernel')/release/'boot-selection.json').read_text())
assert selection['before_boot_id']=='e3b864e5-8239-4a9d-a78f-d0256f2284af'
assert boot!=selection['before_boot_id'], 'Candidate has not booted'
subprocess.run(['mp2-test-no-idle','status'],check=True,capture_output=True)
base=Path('/var/lib/mipad2-kernel')/release
diag=base/'diagnostics'
reportfile=diag/'fresh-audio-audit.json'
diag.mkdir(exist_ok=True)
assert not reportfile.exists()
manifest=json.loads((base/'manifest.json').read_text())
assert manifest['source_commit']=='130c1b76c1aa7761ac570f0342d6c6f77ad8497a'
module=Path('/usr/lib/modules')/release/'kernel/sound/soc/intel/boards/snd-soc-sst-cht-bsw-rt5659.ko.zst'
assert module.exists()
modrel='usr/lib/modules/'+release+'/kernel/sound/soc/intel/boards/'+module.name
assert hashlib.sha256(module.read_bytes()).hexdigest()==manifest['files_sha256'][modrel]
loaded=Path('/sys/module/snd_soc_sst_cht_bsw_rt5659/srcversion').read_text().strip()
assert loaded==subprocess.check_output(['modinfo','-F','srcversion',str(module)],text=True).strip()
graph=Path('/sys/kernel/debug/asoc/cht-bsw-rt5659/i2c-10EC5659:01/dapm/IF2 ADC Mux')
assert '"DAC_REF"' in graph.read_text() and '"IF_ADC2"' not in graph.read_text()
taint=int(Path('/proc/sys/kernel/tainted').read_text().strip())
assert not taint&4096,taint  # no out-of-tree module
user=['runuser','-u','user','--','env','XDG_RUNTIME_DIR=/run/user/1000']
assert not subprocess.check_output(user+['pactl','list','short','sink-inputs'],text=True).strip()
sound=Path('/tmp/mipad2-r24-silence.wav')
with wave.open(str(sound),'wb') as f:
    f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(bytes(48000*2*2*4))
sound.chmod(0o644)
report=dict(release=release,boot_id=boot,source_commit=manifest['source_commit'],
            loaded_srcversion=loaded,taint=taint,mux_repair_performed=False,
            audible_test=False,acoustic_verified=False,initial_graph=graph.read_text(),checks={})
def word(addr,reg,wide=False):
    msg=[f'w2@{addr}',hex(reg>>8),hex(reg&255)] if wide else [f'w1@{addr}',hex(reg)]
    data=subprocess.check_output(['i2ctransfer','-y','-f','1',*msg,'r2'],text=True).strip()
    return int.from_bytes(bytes(int(v,16) for v in data.split()),'big')
def play(label):
    p=subprocess.Popen(user+['pw-play',str(sound)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        time.sleep(1)
        assert p.poll() is None
        state={'dapm_graph':graph.read_text(),'rt5659_hardware':{},'amplifiers':{}}
        assert '"DAC_REF"' in state['dapm_graph']
        for reg,expected in [(0x70,0x8103),(0x71,0),(0x81,0x0f03)]:
            value=word('0x1b',reg,True)
            state['rt5659_hardware'][hex(reg)]=hex(value)
            assert value==expected,(label,reg,value)
        for addr in ('0x34','0x37'):
            status,system=word(addr,0),word(addr,9)
            state['amplifiers'][addr]={'status':hex(status),'system_control':hex(system)}
            assert status&0xc002==0xc002 and not status&0x200,(addr,status)
            assert system&0x9==0x8,(addr,system)
        stdout,stderr=p.communicate(timeout=15)
        assert p.returncode==0,(stdout,stderr)
        time.sleep(7)
        state['idle_system_control']={addr:hex(word(addr,9)) for addr in ('0x34','0x37')}
        assert all(int(value,16)&1 for value in state['idle_system_control'].values())
        report['checks'][label]=state
    finally:
        if p.poll() is None:p.terminate();p.communicate(timeout=5)
try:
    play('fresh_boot_silent_active_and_idle')
    residency=Path('/sys/kernel/debug/pmc_atom/sleep_state')
    report['s0i3_before']=residency.read_text()
    t=time.clock_gettime(time.CLOCK_BOOTTIME)
    p=subprocess.run(['rtcwake','-m','mem','-s','10'],capture_output=True,text=True,timeout=45)
    report['checks']['rtc_s2idle_10s']={'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,
        'boottime_elapsed_seconds':round(time.clock_gettime(time.CLOCK_BOOTTIME)-t,3)}
    assert p.returncode==0
    report['s0i3_after']=residency.read_text()
    time.sleep(3)
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
    play('post_resume_silent_active_and_idle')
    smoke=subprocess.run(['bash','/var/tmp/mipad2-hardware-smoke-r24.sh'],capture_output=True,text=True,timeout=40)
    report['checks']['post_resume_smoke']={'exit_code':smoke.returncode,'stdout':smoke.stdout,'stderr':smoke.stderr}
    assert smoke.returncode==0
    log=subprocess.check_output(['dmesg','--color=never'],text=True)
    (diag/'fresh-audio-audit-dmesg.txt').write_text(log)
    report['kernel_fault_lines']=[l for l in log.splitlines() if any(v in l for v in ('UBSAN:','BUG:','WARNING:','Call Trace:'))]
    assert not report['kernel_fault_lines']
    report['grubenv']=subprocess.check_output(['grub-editenv','/boot/grub/grubenv','list'],text=True)
    assert 'saved_entry=mipad2-bqdiag1' in report['grubenv'] and 'next_entry=\n' in report['grubenv']
    subprocess.run(['mp2-test-no-idle','status'],check=True,capture_output=True)
    report['fresh_boot_and_resume_electrical_passed']=True
finally:
    reportfile.write_text(json.dumps(report,indent=2)+'\n');reportfile.chmod(0o644)
print(json.dumps({k:v for k,v in report.items() if k not in ('checks','initial_graph')},indent=2))
