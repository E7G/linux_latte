# SPDX-License-Identifier: GPL-2.0
import unittest
from mipad2_function_probe import parse, pair, summarize, common


def event(name,ts,pid=10,cpu=0):
    return f'  test-{pid} [{cpu:03d}] ..... 1.{ts:09d}: {name}: (private arguments ignored)'


def fixture():
    return '\n'.join([
        event('c_qbuf_begin',100),event('c_css_queue_begin',110),event('c_css_queue_end',120),event('c_qbuf_end',200),
        event('c_irq_begin',210,pid=11),event('c_irq_end',250,pid=11)])


class ProbeIntervals(unittest.TestCase):
    def test_exact_pair_and_nested_different_functions(self):
        rows=parse(fixture(),'c');calls=pair(rows)
        self.assertEqual({r['role']:r['elapsed_ns'] for r in calls},{'qbuf':100,'css_queue':10,'irq':40})
        self.assertTrue(summarize(rows,calls)['all_entry_return_pairs_complete'])

    def test_integer_microsecond_resolution_and_module_prefix(self):
        row=common('irq/14-isp_irq-32 [002] d.. 12345.123456: mp2:c_irq_begin: (ignored)')
        self.assertEqual((row['pid'],row['ts'],row['resolution_ns']),(32,12345123456000,1000))

    def test_reject_empty_unknown_and_bad_task(self):
        for text in ['',event('c_unknown',1),event('c_qbuf_begin',1,pid=0),'c_qbuf_begin: unknown']:
            with self.subTest(text=text),self.assertRaises(ValueError):parse(text,'c')

    def test_reject_missing_entry_return_and_roles(self):
        normal=fixture().splitlines()
        for rows in [normal[1:],normal[:-1],normal[:4]]:
            with self.assertRaises(ValueError):pair(parse('\n'.join(rows),'c'))

    def test_profile_counts_and_misses_are_mandatory(self):
        rows=parse(fixture(),'c');profile={r['event']:dict(hits=1,missed=0) for r in rows}
        self.assertEqual(len(pair(rows,profile)),3)
        for key,value in [('hits',2),('missed',1)]:
            bad={k:dict(v) for k,v in profile.items()};bad['c_qbuf_begin'][key]=value
            with self.assertRaises(ValueError):pair(rows,bad)

    def test_reject_per_task_clock_reversal(self):
        text=fixture().replace(event('c_qbuf_end',200),event('c_qbuf_end',99))
        with self.assertRaises(ValueError):pair(parse(text,'c'))


if __name__=='__main__':unittest.main()
