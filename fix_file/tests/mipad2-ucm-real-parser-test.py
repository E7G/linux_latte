#!/usr/bin/env python3
"""Actual ALSA UCM parser/sequences with an explicit synthetic control surface.

Requires GCC and ALSA development files. --alsa-root uses an isolated extracted
runtime. No real sound card/PCM, kernel DAPM, jack IRQ or acoustic proof.
"""
from pathlib import Path
import argparse,hashlib,json,os,shlex,subprocess,tempfile

def require(value, message):
    # These are evidence gates, not optional Python debugging assertions.
    if not value:
        raise RuntimeError(message)

parser=argparse.ArgumentParser()
parser.add_argument('--alsa-root',type=Path)
parser.add_argument('--runtime-lib',type=Path)
args=parser.parse_args()
repo=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2]))
pkg=repo/'fix_file/packages/mipad2-alsa-ucm'
fixtures=repo/'fix_file/tests/fixtures'
profiles={n:(pkg/n).read_text() for n in ['cht-bsw-rt5659.conf','HiFi.conf']}
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','alsa'],text=True)) if not args.alsa_root else ['-I'+str(args.alsa_root/'usr/include'),'-L'+str(args.alsa_root/'usr/lib/x86_64-linux-gnu'),'-lasound']
runtime=args.runtime_lib or (args.alsa_root/'usr/lib/x86_64-linux-gnu' if args.alsa_root else None)
rows=[]
with tempfile.TemporaryDirectory(prefix='mipad2-ucm-actual-parser-') as directory:
    base=Path(directory)
    common=['gcc','-g','-O1','-Wall','-Wextra','-Werror','-Wno-misleading-indentation']
    for source,dest,extra in [('mipad2-ucm-ctl-ext.c','libasound_module_ctl_mp2test.so',['-fPIC','-DPIC','-shared']),('mipad2-ucm-sequence-runner.c','runner',[])]:
        q=subprocess.run([*common,*extra,str(fixtures/source),*flags,'-o',str(base/dest)],capture_output=True,text=True)
        require(q.returncode == 0, q.stderr)
    (base/'alsa.conf').write_text('ctl.hw { @args [ CARD ] @args.CARD { type string } type mp2test }\n')
    ucm=base/'ucm';(ucm/'test').mkdir(parents=True)
    (ucm/'ucm.conf').write_text('Syntax 3\nUseCasePath.test { Directory "test" File "test.conf" }\n')
    (ucm/'test/test.conf').write_text(profiles['cht-bsw-rt5659.conf'])
    (ucm/'test/HiFi.conf').write_text(profiles['HiFi.conf'])
    def run(layout,tag):
        log=base/(tag+'.controls')
        env=dict(os.environ,ALSA_PLUGIN_DIR=str(base),ALSA_CONFIG_PATH=str(base/'alsa.conf'),ALSA_CONFIG_UCM2=str(ucm),MP2_CTL_LAYOUT=layout,MP2_CTL_LOG=str(log))
        if runtime:env['LD_LIBRARY_PATH']=str(runtime)
        q=subprocess.run([str(base/'runner')],capture_output=True,text=True,env=env,timeout=30)
        return q,log.read_text().splitlines() if log.exists() else []
    for layout in ['modern','legacy','both','missing_right','legacy_missing_right','missing_left','mixed_right','none']:
        q,writes=run(layout,layout)
        positive=layout in ['modern','legacy','both']
        left='Amp Input|0' if layout=='legacy' else 'Left Amp Input|0'
        right='Amp Input1|1' if layout=='legacy' else 'Right Amp Input|1'
        if positive:
            require(q.returncode == 0, (layout, q.stderr))
            amps=[x for x in writes if 'Amp Input' in x]
            require(amps == [left, right] * 3, (layout, amps))
            for i,x in enumerate(writes):
                if x=='Ext Spk Switch|1':require(writes[i - 3:i] == [left, right, 'Headphone Switch|0'], (layout, i, writes[i - 3:i]))
            require(q.stdout.startswith('real ALSA '), q.stdout)
        else:
            require(q.returncode == 10 and (not writes), (layout, q.returncode, writes, q.stderr))
        rows.append(dict(layout=layout,exit_code=q.returncode,passed=True,mixer_write_count=len(writes),sequence_summary=q.stdout.strip(),partial_or_unknown_rejected_before_writes=not positive))
    # Mutate only the temporary configuration to select the left amplifier for
    # both channels. ALSA accepts it, but the independent channel oracle must not.
    wrong=profiles['HiFi.conf'].replace("${var:RightAmpControl}' Right","${var:LeftAmpControl}' Right")
    require(wrong != profiles['HiFi.conf'], 'UCM oracle invariant failed at original line 56')
    (ucm/'test/HiFi.conf').write_text(wrong)
    q,writes=run('modern','wrong-channel-negative')
    amps=[x for x in writes if 'Amp Input' in x]
    require(q.returncode == 0 and amps != ['Left Amp Input|0', 'Right Amp Input|1'] * 3, 'UCM oracle invariant failed at original line 60')
    require(amps == ['Left Amp Input|0', 'Left Amp Input|1'] * 3, amps)
result=dict(state='real-ALSA-UCM-layout-and-channel-oracles-pass',cases=rows,wrong_channel_mutation_detected=True,profile_sha256={n:hashlib.sha256(s.encode()).hexdigest() for n,s in profiles.items()},scope='Real libasound ControlExists/substitution/parser/sequence/ctl_ext APIs with explicitly synthetic controls. No physical PCM, DAPM, jack or acoustic validation.',hardware_tested=False)
print(json.dumps(result,indent=2))
