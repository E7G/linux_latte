"""Exact encodebin input-queue witnesses. Arrival times, not isolated residence."""
from collections import defaultdict
from mipad2_raw_tail_arrivals import analyze as raw_analyze
from mipad2_frame_arrivals_v3 import require, stats, _within, _key

QUEUE='/GstEncodeBin:video-encodebin/GstQueue:queue2.GstPad:'

def analyze(rows, keys):
    keys=[_key(k) for k in keys]
    common=raw_analyze(rows,keys,'raw-direct')
    frames=defaultdict(list)
    for row in rows:
        if row.get('operation') in ('chain','push'):
            frames[(row['pts'],row['offset'])].append(row)
    samples=defaultdict(list);non_ok=defaultdict(int);early=0
    for key in keys:
        frame=frames[key]
        def select(op,klass,suffix):
            items=[r for r in frame if r['operation']==op and r['path'].startswith(klass+'\t') and r['path'].endswith(suffix)]
            require(len(items)==1,'Missing or ambiguous encode input queue boundary')
            return items[0]
        native=select('push','GstV4l2Src','.GstPad:src')
        raw=select('push','GstCapsFilter','mipad2-native-raw-output.GstPad:src')
        sink=select('chain','GstQueue',QUEUE+'sink')
        worker=select('push','GstQueue',QUEUE+'src')
        enc=select('chain','GstVaH264Enc','.GstPad:sink')
        require(_within(sink,raw),'Encode queue enqueue not nested on native raw output')
        require(worker['tid']!=native['tid'],'Encode input queue worker did not change task')
        require(_within(enc,worker),'Encoder not nested on encode queue worker')
        cuts=[native['begin'],raw['begin'],sink['begin'],worker['begin'],enc['begin']]
        values=[b-a for a,b in zip(cuts,cuts[1:])]
        require(all(v>=0 for v in values),'Encode queue arrival ordering reversed')
        require(sum(values)==enc['begin']-native['begin'],'Encode queue exact partition failed')
        for label,value in zip(('source_to_raw_output','raw_output_to_encode_queue_sink','encode_queue_sink_to_worker_begin','encode_queue_worker_to_encoder'),values):samples[label].append(value)
        samples['encode_queue_sink_chain_wall'].append(sink['elapsed_ns'])
        samples['encode_queue_worker_push_wall'].append(worker['elapsed_ns'])
        non_ok['encode-queue-sink']+=sink['result']!=0
        non_ok['encode-queue-worker']+=worker['result']!=0
        early+=worker['begin']<sink['end']
    result={n:dict(stats(v),above40ms=sum(x>40_000_000 for x in v),above100ms=sum(x>100_000_000 for x in v)) for n,v in samples.items()}
    result.update(frames=len(keys),exact_partition=True,all_named_queue_witnesses=True,queue_worker_begins_before_sink_return=early,non_ok_flow_counts=dict(non_ok),
                  source_to_encoder_arrival=common['native_push_to_encoder_chain'],
                  queue_capacity_proven=False,isolated_queue_residence_proven=False,no_payload_read=True,
                  scope='Actual named video-encodebin queue2 sink-arrival to worker-push interval includes blocking enqueue; not isolated residence/CPU, capacity, optical latency or Android parity. Every selected frame retained.')
    return result
