import unittest
from mipad2_frame_chain_join import exact_subset, require_ordered_bijection, running_time_rate_one, quantize_ns, segment_event_success


class JoinTests(unittest.TestCase):
    def test_event_result_types(self):
        for op,result,expected in [('send-event',0,True),('send-event',1,False),('send-event',-1,False),('push-event',1,True),('push-event',0,False)]:
            self.assertEqual(segment_event_success(dict(operation=op,result=result,argument=17934)),expected)
        self.assertFalse(segment_event_success(dict(operation='push-event',result=1,argument=0)))

    def test_exact_subset(self):
        a,b=exact_subset([2,3],[1,2,3,4],lambda x:x,lambda x:x)
        self.assertEqual(a,[(2,2),(3,3)]);self.assertEqual(b,2)

    def test_reject_missing_duplicate_reorder_and_extra(self):
        for a,b in [([1],[2]),([1,1],[1]),([1],[1,1]),([1,2],[2,1])]:
            with self.assertRaises(ValueError):exact_subset(a,b,lambda x:x,lambda x:x)
        with self.assertRaises(ValueError):require_ordered_bijection([1],[1,2],lambda x:x,lambda x:x)

    def test_segment_is_observed_not_fitted(self):
        s=dict(format=3,rate=1.0,applied_rate=1.0,start=100,offset=20,base=7,time=900)
        self.assertEqual(running_time_rate_one(123,s),10)
        self.assertEqual(running_time_rate_one(100,s),-13)
        for k,v in [('format',2),('rate',2.0),('applied_rate',0.5),('start',-1),('offset',2**64-1)]:
            with self.assertRaises(ValueError):running_time_rate_one(123,dict(s,**{k:v}))

    def test_timescale_rounding_not_fps_guess(self):
        self.assertEqual(quantize_ns(33333333,1,3000),100)
        self.assertEqual(quantize_ns(500000000,1,3),2)
        self.assertEqual(quantize_ns(1000000000,1001,30000),30)
        for args in [(-1,1,3000),(1,0,3000),(1,1,0)]:
            with self.assertRaises(ValueError):quantize_ns(*args)


if __name__=='__main__':unittest.main()
