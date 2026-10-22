import unittest
from mipad2_kernel_fault_patterns import count_faults

class FaultPatterns(unittest.TestCase):
    def test_debug_and_embedded_suffixes_are_not_faults(self):
        lines=['[0.0] printk: debug: ignoring loglevel setting.',
               'debug: details', 'DEBUG: details', 'dynamic_debug: setup',
               'nodebug: value', 'myBUG: string', '_BUG: string',
               'embeddedWARNING: text', 'myOops: value', 'prefixGPU HANG',
               'CONFIG_DEBUG=y', 'kernel debugger initialized']
        for line in lines:
            with self.subTest(line=line):self.assertFalse(any(count_faults(line).values()))

    def test_real_bug_headers_still_match(self):
        lines=['[1.0] BUG: sleeping function called from invalid context',
               'BUG: KASAN: use-after-free', 'kernel BUG at mm/file.c:10!',
               '[3.1] kernel BUG!', '<0>BUG: bad page state',
               'BUG: unable to handle page fault', 'kernel bug at driver.c:4']
        for line in lines:
            with self.subTest(line=line):self.assertEqual(count_faults(line)['BUG'],1)

    def test_other_actual_fault_labels(self):
        for text,key in [('[4] WARNING: CPU: 0','WARNING'),
                         ('[4] Oops: 0002 [#1]','Oops'),
                         ('[4] i915: GPU HANG: engine','GPU HANG')]:
            with self.subTest(text=text):self.assertEqual(count_faults(text)[key],1)

    def test_no_trimming_and_multiple_faults(self):
        text='debug: boot\nBUG: early failure\n'+('normal\n'*1000)+'kernel BUG at late.c:2\nOops: fault\n'
        self.assertEqual(count_faults(text),{'BUG':2,'WARNING':0,'Oops':1,'GPU HANG':0})

if __name__=='__main__':unittest.main()
