import copy,json,unittest
from test_mipad2_raw_tail_arrivals import raw_frame
from test_mipad2_frame_arrivals_v3 import call
from mipad2_encode_queue_arrivals import analyze,QUEUE

def fixture():
    return raw_frame('raw-direct')+[
        call('chain','GstQueue',QUEUE+'sink',50,70),
        call('push','GstQueue',QUEUE+'src',90,110,4)]

class EncodeQueue(unittest.TestCase):
    def test_exact_partition(self):
        r=analyze(fixture(),[(10,2)])
        self.assertEqual([r[x]['median_ns'] for x in ['source_to_raw_output','raw_output_to_encode_queue_sink','encode_queue_sink_to_worker_begin','encode_queue_worker_to_encoder']],[40,10,40,10])
        self.assertFalse(r['isolated_queue_residence_proven'])

    def test_overlapping_enqueue_permitted(self):
        rows=fixture();rows[-2].update(end=95,elapsed_ns=45)
        # Keep enqueue nested inside its calling raw push and native guard.
        rows[0].update(end=140,elapsed_ns=140);rows[1].update(end=130,elapsed_ns=110);rows[2].update(end=120,elapsed_ns=95);rows[4].update(end=100,elapsed_ns=60)
        self.assertEqual(analyze(rows,[(10,2)])['queue_worker_begins_before_sink_return'],1)

    def test_missing_duplicate_or_wrong_parent(self):
        for i in (5,6):
            rows=fixture()
            with self.assertRaises(ValueError):analyze(rows[:i]+rows[i+1:],[(10,2)])
            with self.assertRaises(ValueError):analyze(rows+[copy.deepcopy(rows[i])],[(10,2)])
            rows[i]['path']=rows[i]['path'].replace('video-encodebin','image-encodebin')
            with self.assertRaises(ValueError):analyze(rows,[(10,2)])

    def test_order_task_and_nesting_fail_closed(self):
        for i,change in [(5,dict(tid=2)),(6,dict(tid=1)),(6,dict(begin=40,end=110,elapsed_ns=70)),(6,dict(end=103,elapsed_ns=13))]:
            rows=fixture();rows[i].update(change)
            with self.subTest(change=change):
                with self.assertRaises(ValueError):analyze(rows,[(10,2)])

    def test_nonok_retained(self):
        rows=fixture();rows[-1]['result']=-2
        self.assertEqual(analyze(rows,[(10,2)])['non_ok_flow_counts']['encode-queue-worker'],1)

    def test_all_frames_and_no_owner_export(self):
        rows=[];keys=[]
        for i in range(9):
            keys.append((10+i,2+i))
            for r in fixture():
                r.update(pts=10+i,offset=2+i,begin=r['begin']+i*1000,end=r['end']+i*1000);rows.append(r)
        out=analyze(rows,keys);self.assertEqual(out['frames'],9)
        self.assertTrue(all(v['count']==9 for v in out.values() if isinstance(v,dict) and 'count' in v))
        for forbidden in ['"tid"','"pts"','"offset"','"path"','fixture/']:self.assertNotIn(forbidden,json.dumps(out))

    def test_invalid_identity_clock_and_empty_rejected(self):
        for keys in [[],[(10,2),(10,2)],[(11,2)]]:
            with self.assertRaises(ValueError):analyze(fixture(),keys)
        rows=fixture();rows[-1]['elapsed_ns']=900
        with self.assertRaises(ValueError):analyze(rows,[(10,2)])

if __name__=='__main__':unittest.main(verbosity=2)
