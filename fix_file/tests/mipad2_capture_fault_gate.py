# SPDX-License-Identifier: GPL-2.0
"""Strict additional kernel/source-error gate; does not qualify cadence or quality."""
import re
PATTERNS={
 'FW_ASSERT':r'\bFW_ASSERT event!',
 'GPU_HANG':r'GPU HANG',
 'panic':r'Kernel panic',
 'BUG':r'(?<!\w)(?:BUG:|kernel BUG at\b|kernel BUG!)',
 'Oops':r'(?<!\w)Oops:',
 'WARNING':r'(?<!\w)WARNING:',
 'DDR':r'Failed to (?:disable|enable) DDR DVFS',
 'IUNIT':r'IUNIT power-(?:on|off) timeout',
 'CSS_queue':r'css q fails|invalid PSYS event type',
 'SP_not_idle':r'SP is not idle',
 'ISP_not_idle':r'ISP is not idle',
 'stop_timeout':r'stop stream timeout',
 'recovery_failed':r'Stream (?:reset/recreate|recovery) failed',
}
def require(v,message):
 if not v:raise ValueError(message)
def scan(text):
 require(type(text) is str and len(text)<=32*1024**2,'Bounded kernel text required')
 return {name:len(re.findall(pattern,text,re.I)) for name,pattern in PATTERNS.items()}
def check(before,after,*,errored_source_frames):
 require(type(errored_source_frames) is int and errored_source_frames>=0,'Explicit nonnegative source-error count required')
 old=scan(before);new=scan(after);continuous=after.startswith(before)
 delta={name:new[name]-old[name] for name in PATTERNS} if continuous else None
 require(delta is None or all(n>=0 for n in delta.values()),'Append-only kernel count contradiction')
 reasons=[]
 if not continuous:reasons.append('kernel-log-history-not-continuous')
 if delta is not None:reasons.extend('new-kernel-'+name for name,n in delta.items() if n)
 if errored_source_frames:reasons.append('errored-source-frame-delivered')
 return dict(state='capture-fatal-and-source-error-gate',pass_gate=not reasons,kernel_history_continuous=continuous,new_fault_counts=delta,errored_source_frames=errored_source_frames,reasons=reasons,scope='additional fatal/source gate only; not cadence, pixels, timing identity or OEM qualification')
def selftest():
 base='[ 1.000] starting\n';assertion='[ 2.000] atomisp: ISP reports FW_ASSERT event! fw_assert_module_id 255 fw_assert_line_no 291\n'
 require(check(base,base+'[ 2.000] ready\n',errored_source_frames=0)['pass_gate'],'Clean case rejected')
 require(not check(base,base+assertion,errored_source_frames=0)['pass_gate'],'FW assertion accepted')
 require(not check(base,base,errored_source_frames=1)['pass_gate'],'Corrupt source accepted')
 require(check(base+assertion,base+assertion+'[ 3.000] ready\n',errored_source_frames=0)['pass_gate'],'Historical fault treated as new')
 require(not check(base,'[ 3.000] rotated\n',errored_source_frames=0)['pass_gate'],'Log rotation accepted')
 require(check(base,base+assertion,errored_source_frames=1)['new_fault_counts']['FW_ASSERT']==1,'Assertion count lost')
 for name,example in [('GPU_HANG','GPU HANG'),('panic','Kernel panic'),('BUG','BUG:'),('Oops','Oops:'),('WARNING','WARNING:'),('DDR','Failed to enable DDR DVFS'),('IUNIT','IUNIT power-off timeout'),('CSS_queue','css q fails'),('CSS_queue','Invalid PSYS event type 255'),('CSS_queue','ISP returned an invalid PSYS event type'),('SP_not_idle','SP is not idle'),('ISP_not_idle','ISP is not idle'),('stop_timeout','stop stream timeout'),('recovery_failed','Stream recovery failed')]:
  r=check(base,base+example+'\n',errored_source_frames=0);require(not r['pass_gate'] and r['new_fault_counts'][name]==1,'Fault accepted '+name)
 rejected=0
 for value in [-1,True,None,1.0]:
  try:check(base,base,errored_source_frames=value)
  except ValueError:rejected+=1;continue
  raise AssertionError('Invalid source count accepted')
 return dict(tests=24,all_new_FW_assertions_and_source_errors_fail=True,log_rotation_not_treated_as_clean=True,malformed_negative_controls=rejected)
if __name__=='__main__':
 import argparse,json,sys
 from pathlib import Path
 if len(sys.argv)==1:
  print(json.dumps(selftest()))
 else:
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--before',type=Path,required=True)
  parser.add_argument('--after',type=Path,required=True)
  parser.add_argument('--source-error-frames',type=int,required=True)
  args=parser.parse_args()
  result=check(args.before.read_text(),args.after.read_text(),errored_source_frames=args.source_error_frames)
  print(json.dumps(result))
  raise SystemExit(0 if result['pass_gate'] else 1)
