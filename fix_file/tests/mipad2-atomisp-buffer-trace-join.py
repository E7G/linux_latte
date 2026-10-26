#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Strict metadata-only trace -> native DQBUF join. Raw records stay private."""
import collections,csv,io,re,statistics
FIELDS=('minor','index','sequence','exp_id','isp_config_id','state','timestamp_ns','bytesused')
LINE=re.compile(r'\s(\d+)\.(\d{1,9}):\s+(?:atomisp:)?atomisp_buffer_done:\s+(.*)$')

def parse_trace(text):
 rows=[]
 for line in text.splitlines():
  if 'atomisp_buffer_done:' not in line:continue
  m=LINE.search(line)
  if not m:raise ValueError('Unrecognized event prefix')
  words=m[3].split()
  if len(words)!=8:raise ValueError('Event field count')
  values={}
  for name,word in zip(FIELDS,words):
   pair=word.split('=')
   if len(pair)!=2 or pair[0]!=name or not re.fullmatch(r'\d+',pair[1]):raise ValueError('Event schema/order')
   values[name]=int(pair[1])
  if not (values['minor']<256 and values['index']<32 and values['sequence']<2**32 and values['exp_id']<=250 and values['isp_config_id']<2**32 and values['state']<=6 and values['timestamp_ns']<2**64 and values['bytesused']<=24*1024**2):raise ValueError('Field out of bounds')
  values['trace_ns']=int(m[1])*10**9+int(m[2].ljust(9,'0'))
  if values['state']==5 and not (values['timestamp_ns'] and values['bytesused']):raise ValueError('Invalid DONE identity')
  rows.append(values)
 if not rows:raise ValueError('No trace events')
 return rows

def parse_csv(text,frames=120,phases=4):
 f=csv.DictReader(io.StringIO(text))
 if f.fieldnames!=['phase','sequence','index','bytes','timestamp_us']:raise ValueError('Native CSV schema')
 rows=[];last={}
 for row in f:
  if any(not isinstance(v,str) or not re.fullmatch(r'\d+',v) for v in row.values()):raise ValueError('Native value')
  r={k:int(v) for k,v in row.items()}
  if not (r['phase']<phases and r['index']<32 and r['sequence']<2**32 and 0<r['bytes']<=24*1024**2 and r['timestamp_us']>0):raise ValueError('Native bounds')
  prior=last.get(r['phase'])
  if prior and (r['sequence']!=prior['sequence']+1 or r['timestamp_us']<=prior['timestamp_us']):raise ValueError('Native sequence/timestamp discontinuity')
  last[r['phase']]=r;rows.append(r)
 if collections.Counter(r['phase'] for r in rows)!={i:frames for i in range(phases)}:raise ValueError('Native phase/frame counts')
 return rows

def join(trace,native,minor=0):
 def key(r,native=False):
  return (r['sequence'],r['index'],r['bytes'] if native else r['bytesused'],r['timestamp_us'] if native else r['timestamp_ns']//1000)
 candidates=collections.defaultdict(list)
 for r in trace:
  if r['state']==5 and r['minor']==minor:candidates[key(r)].append(r)
 matched=[];seen=set()
 for row in native:
  k=key(row,True)
  if k in seen or len(candidates[k])!=1:raise ValueError('Missing/ambiguous/duplicate exact DQBUF identity')
  seen.add(k);matched.append(candidates[k][0])
 latency=[r['trace_ns']-r['timestamp_ns'] for r in matched]
 if min(latency)<-1000:raise ValueError('Trace clock precedes buffer timestamp')
 return dict(native_frames=len(native),exact_unique_matches=len(matched),done_trace_events=len([r for r in trace if r['state']==5 and r['minor']==minor]),extra_DONE_not_dequeued=len(candidates)-len(seen),trace_states=dict(collections.Counter(r['state'] for r in trace)),matched_nonzero_CSS_exposure_ids=sum(bool(r['exp_id']) for r in matched),matched_zero_CSS_exposure_ids=sum(r['exp_id']==0 for r in matched),CSS_ID_correspondence_complete=all(r['exp_id']!=0 for r in matched),completion_minus_buffer_timestamp_ns=dict(min=min(latency),median=statistics.median(latency),max=max(latency)),identity_fields=['minor','sequence','index','bytesused','floor(timestamp_ns/1000)'],physical_sensor_frame_conservation_proved=False,encoder_or_MP4_identity_proved=False)

def selftest():
 text='probe-1 [000] .... 10.123456: atomisp_buffer_done: minor=0 index=1 sequence=2 exp_id=250 isp_config_id=0 state=5 timestamp_ns=10123000123 bytesused=3110400\n'
 native='phase,sequence,index,bytes,timestamp_us\n0,2,1,3110400,10123000\n'
 assert join(parse_trace(text),parse_csv(native,1,1))['exact_unique_matches']==1
 assert join(parse_trace(text.replace('exp_id=250','exp_id=0')),parse_csv(native,1,1))['CSS_ID_correspondence_complete'] is False
 cases=[lambda:parse_trace(text.replace('state=5','state=9')),lambda:parse_trace(text.replace('exp_id=250','exp_id=251')),lambda:parse_trace(text.replace('bytesused=3110400','index=1')),lambda:join(parse_trace(text*2),parse_csv(native,1,1)),lambda:join(parse_trace(text.replace('state=5','state=6')),parse_csv(native,1,1)),lambda:join(parse_trace(text),parse_csv(native.replace(',1,3110400',',2,3110400'),1,1)),lambda:parse_csv(native,2,1),lambda:parse_trace('')]
 for fn in cases:
  try:fn()
  except ValueError:continue
  raise AssertionError('Negative control accepted')
 return dict(valid_exact_join=1,negative_controls_rejected=len(cases),float_timestamps_used=False,raw_media_access=False)

if __name__ == '__main__':
 import argparse,json
 from pathlib import Path
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--selftest',action='store_true')
 p.add_argument('--trace',type=Path)
 p.add_argument('--native',action='append',default=[],metavar='NAME:CSV')
 p.add_argument('--minor',type=int,default=0)
 p.add_argument('--frames',type=int,default=120)
 p.add_argument('--phases',type=int,default=4)
 a=p.parse_args()
 if a.selftest:
  print(json.dumps(dict(**selftest(),zero_CSS_id_retained_without_CSS_correspondence_claim=True)))
 else:
  if not a.trace or not a.native:p.error('--trace and --native NAME:CSV required')
  if a.frames<=0 or a.phases<=0 or a.minor<0:p.error('positive frames/phases and nonnegative minor required')
  trace=parse_trace(a.trace.read_text());native=[];cameras={}
  for arg in a.native:
   name,sep,path=arg.partition(':')
   if not sep or not name or name in cameras:p.error('unique NAME:CSV required')
   rows=parse_csv(Path(path).read_text(),a.frames,a.phases)
   cameras[name]=join(trace,rows,a.minor);native+=rows
  print(json.dumps(dict(all_native=join(trace,native,a.minor),subsets=cameras,
   subset_extra_DONE_scope='other native subsets also appear in the same trace; not a drop counter',
   sensor_physical_or_encoder_frame_conservation_proved=False,raw_records_exported=False),indent=2))
