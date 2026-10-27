LEGACY_EVENT_SHA='b68fd4df0c04d088f63173ee8d42ea86f86f0483aa7a822941093efcc4bc2ff9'
ORIGINAL_CMD_SHA='a31a8164a29e67030beb96e5a12e618d8660cec66b7b03fd4fcf198c2bd25094'
CALL_BLOCK=');\n\t\tif (buf_type == IA_CSS_BUFFER_TYPE_OUTPUT_FRAME ||\n\t\t    buf_type == IA_CSS_BUFFER_TYPE_VF_OUTPUT_FRAME)\n\t\t\ttrace_atomisp_css_frame_timing(pipe->vdev.minor,\n\t\t\t\tframe->vb.vb2_buf.index, buf_type, frame->exp_id,\n\t\t\t\tframe->isp_config_id,\n\t\t\t\tbuffer.css_buffer.isys_eof_clock_tick.ticks,\n\t\t\t\tbuffer.css_buffer.timing_data.start_timer_value,\n\t\t\t\tbuffer.css_buffer.timing_data.end_timer_value'

# SPDX-License-Identifier: GPL-2.0
"""Source-level additive-trace invariants; not hardware or frame-rate qualification."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess,sys,tempfile,unittest
root=Path(__file__).resolve().parents[2]
cmd=(root/'drivers/staging/media/atomisp/pci/atomisp_cmd.c').read_text()
header=(root/'drivers/staging/media/atomisp/pci/atomisp_trace_event.h').read_text()
def event(text,name):
 a=text.index('TRACE_EVENT('+name+',');return text[a:text.index('\n);\n',a)+4]
spec=importlib.util.spec_from_file_location('fault_gate',Path(__file__).with_name('mipad2_capture_fault_gate.py'));gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
class TimingTrace(unittest.TestCase):
 def test_legacy_completion_event_unchanged(self):self.assertEqual(hashlib.sha256(event(header,'atomisp_buffer_done').encode()).hexdigest(),LEGACY_EVENT_SHA)
 def test_original_capture_math_and_timestamp_unchanged(self):self.assertEqual(hashlib.sha256(cmd.replace(CALL_BLOCK,'').encode()).hexdigest(),ORIGINAL_CMD_SHA)
 def test_supported_buffer_types_and_lock_scope(self):
  start=cmd.index('void atomisp_buf_done(');end=cmd.index('void atomisp_assert_recovery_work(',start);body=cmd[start:end]
  trace=body.index('trace_atomisp_css_frame_timing(');lock=body.rfind('spin_lock_irqsave(&pipe->irq_lock',0,trace);done=body.index('atomisp_buffer_done(frame,',trace);unlock=body.index('spin_unlock_irqrestore(&pipe->irq_lock',done)
  self.assertLess(lock,trace);self.assertLess(trace,done);self.assertLess(done,unlock);self.assertIn('buf_type == IA_CSS_BUFFER_TYPE_OUTPUT_FRAME ||',CALL_BLOCK);self.assertIn('buf_type == IA_CSS_BUFFER_TYPE_VF_OUTPUT_FRAME)',CALL_BLOCK)
 def test_raw_metadata_only_no_clock_conversion(self):
  e=event(header,'atomisp_css_frame_timing');fields=set(re.findall(r'__field\([^,]+,\s*(\w+)\)',e));self.assertEqual(fields,{'minor','index','buf_type','exp_id','isp_config_id','eof_tick','start_tick','end_tick'})
  for field in ['eof_tick','start_tick','end_tick']:self.assertIn('__field(u32, '+field+')',e)
  self.assertNotIn('__string',e);self.assertNotIn('__array',e);self.assertNotIn('320',CALL_BLOCK);self.assertNotIn('ktime_get',CALL_BLOCK)
class CaptureFaultGate(unittest.TestCase):
 def test_all_negative_controls(self):self.assertEqual(gate.selftest()['tests'],24)
 def test_corrupt_source_without_kernel_warning_fails(self):self.assertFalse(gate.check('boot\n','boot\n',errored_source_frames=1)['pass_gate'])
 def test_FWassert_is_not_a_successful_decode(self):
  r=gate.check('boot\n','boot\nISP reports FW_ASSERT event! fw_assert_module_id 255 fw_assert_line_no 291\n',errored_source_frames=0);self.assertFalse(r['pass_gate']);self.assertEqual(r['new_fault_counts']['FW_ASSERT'],1)
 def test_invalid_psys_protocol_is_fatal(self):
  for text in ['Invalid PSYS event type 255','ISP returned an invalid PSYS event type']:
   r=gate.check('boot\n','boot\n'+text+'\n',errored_source_frames=0);self.assertFalse(r['pass_gate']);self.assertEqual(r['new_fault_counts']['CSS_queue'],1)
 def test_historical_protocol_error_is_not_new(self):
  before='boot\nInvalid PSYS event type 255\n';r=gate.check(before,before+'ready\n',errored_source_frames=0);self.assertTrue(r['pass_gate']);self.assertEqual(r['new_fault_counts']['CSS_queue'],0)
 def test_command_line_failure_and_clean_exit(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'before';b=Path(d)/'after';a.write_text('boot\n');b.write_text('boot\nFW_ASSERT event!\n');script=Path(__file__).with_name('mipad2_capture_fault_gate.py')
   p=subprocess.run([sys.executable,str(script),'--before',str(a),'--after',str(b),'--source-error-frames','0'],capture_output=True,text=True);self.assertEqual(p.returncode,1);self.assertFalse(json.loads(p.stdout)['pass_gate'])
   b.write_text('boot\nready\n');p=subprocess.run([sys.executable,str(script),'--before',str(a),'--after',str(b),'--source-error-frames','0'],capture_output=True,text=True);self.assertEqual(p.returncode,0)
if __name__=='__main__':unittest.main()
