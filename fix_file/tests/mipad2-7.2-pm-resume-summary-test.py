"""Bounded scalar consistency/negative oracles; does not execute hardware sleep.

Reuses the existing raw production-fixture gate, not a substitute frame model.
Pass means a bounded sleep+raw-reopen sample, never complete device acceptance.
"""
import ast
import copy
import json
import math
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
text=(HERE/'mipad2-7.2-r3-lifecycle-host-test.py').read_text()
node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='strict_result_pass')
namespace={}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<existing-raw-fixture-gate>','exec'),namespace)
raw_pass=namespace['strict_result_pass']


def cycle_pass(cycle):
    try:
        s=cycle['suspend'];r=cycle['reopen']
        if s['state']!='resume-gates-passed' or s['terminal'] is not True or s['rtcwake_exit']!=0 or s['boot_unchanged'] is not True:
            return False
        request=s['requested_seconds'];elapsed=s['boottime_elapsed'];slept=s['estimated_suspended_seconds'];res=s['s0i3_delta_us']
        if not all(type(v) in (int,float) and math.isfinite(v) for v in [request,elapsed,slept,res]):
            return False
        if request!=12 or not .7*request<=slept<=request+8 or not .7*request*1000000<=res<=(elapsed+3)*1500000:
            return False
        if s['remaining_rtc_alarm'] not in ['', '0']:
            return False
        if s['unit']!=dict(ActiveState='inactive',SubState='dead',MainPID='0',Result='success',ExecMainStatus='0'):
            return False
        needed={'panic','BUG','WARNING','Oops','GPU_HANG','DDR_failure','IUNIT_timeout','stop_timeout','SP_not_idle','ISP_not_idle','reset_failed','TFA_DSP_timeout'}
        faults=s['kernel_fault_delta']
        if not needed<=faults.keys() or any(type(x) is not int or x!=0 for x in faults.values()):
            return False
        for pm in [s['before_pm'],s['after_pm'],r['pm']]:
            if set(pm)!={'t4ka3','ov5693','isp'} or any(v!=dict(runtime_status='suspended',runtime_usage='0') for v in pm.values()):
                return False
        if r['state']!='passed' or r['child_live_now'] is not False or r['original_input_format_controls_restored'] is not True or r['sensor_geometry_restored'] is not True:
            return False
        if r['capture_profile']!='1920x1080-NV12' or r['after_system_s2idle_test'] is not True:
            return False
        if r['source_sha256']!='21d2778795f0017ca788c6320e2724d13e7b195cb8abde42dfef19d87fa39cca' or r['binary_sha256']!='34d4cfd3268fc65c6e8ed1b4fa46634b68de560fd35ee5835c3ec9afca2a8398':
            return False
        if not r['kernel_fault_delta'] or any(type(x) is not int or x!=0 for x in r['kernel_fault_delta'].values()):
            return False
        if len(r['cases'])!=2 or {x['camera'] for x in r['cases']}!={'front','rear'}:
            return False
        for case in r['cases']:
            if not raw_pass(case['result']) or case['passed'] is not True or case['exit']!=0:
                return False
            if case['shape_preserved'] is not True or case['sensor_controls_preserved'] is not True:
                return False
            if (case['result']['width'],case['result']['height'],case['result']['pixel_format'])!=(1920,1080,842094158):
                return False
            if case['phase_frame_counts']!={str(i):120 for i in range(4)}:
                return False
            if any(type(x) is not int or x!=0 for x in case['kernel_fault_delta'].values()):
                return False
        return True
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        return False


class PMResumeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((HERE/'mipad2-7.2-pm-resume-summary.json').read_text())

    def cycle(self):
        return copy.deepcopy(self.report['cycles'][0])

    def test_actual_both_bounded_cycles(self):
        self.assertEqual(len(self.report['cycles']),2)
        self.assertTrue(all(cycle_pass(x) for x in self.report['cycles']))

    def test_rtcwake_exit_zero_not_enough_without_residency(self):
        c=self.cycle();c['suspend']['s0i3_delta_us']=0
        self.assertFalse(cycle_pass(c))

    def test_wrong_unit_or_boot_not_a_success(self):
        c=self.cycle();c['suspend']['unit']['MainPID']='99'
        self.assertFalse(cycle_pass(c))
        c=self.cycle();c['suspend']['boot_unchanged']=False
        self.assertFalse(cycle_pass(c))

    def test_kernel_warning_or_active_pm_reject(self):
        c=self.cycle();c['suspend']['kernel_fault_delta']['WARNING']=1
        self.assertFalse(cycle_pass(c))
        c=self.cycle();c['reopen']['pm']['isp']['runtime_usage']='1'
        self.assertFalse(cycle_pass(c))

    def test_c_exit_zero_with_sequence_gap_still_rejects(self):
        c=self.cycle();c['reopen']['cases'][0]['result']['phases'][0]['sequence_discontinuities']=1
        self.assertFalse(cycle_pass(c))

    def test_leftover_alarm_or_live_child_reject(self):
        c=self.cycle();c['suspend']['remaining_rtc_alarm']='12345'
        self.assertFalse(cycle_pass(c))
        c=self.cycle();c['reopen']['child_live_now']=True
        self.assertFalse(cycle_pass(c))

    def test_geometry_restore_failure_rejects(self):
        c=self.cycle();c['reopen']['sensor_geometry_restored']=False
        self.assertFalse(cycle_pass(c))
        c=self.cycle();c['reopen']['cases'][0]['result']['width']=640
        self.assertFalse(cycle_pass(c))
        c=self.cycle();c['reopen']['kernel_fault_delta']['WARNING']=1
        self.assertFalse(cycle_pass(c))

    def test_nonfinite_or_boolean_measurement_rejects(self):
        for value in [float('nan'),float('inf'),True,'12']:
            c=self.cycle();c['suspend']['estimated_suspended_seconds']=value
            self.assertFalse(cycle_pass(c))

    def test_shared_irq_is_not_unique_rtc_attribution(self):
        self.assertIs(self.report['first_shared_irq_not_unique_rtc_attribution'],True)
        self.assertEqual(self.report['second_acpi_rtc_fixed_event_delta'],1)
        self.assertTrue(all(x['suspend']['actual_wakeup_irq']=='9' for x in self.report['cycles']))

    def test_bounded_raw_evidence_never_oem_or_codec_acceptance(self):
        for k in ['stable_or_oem_promotion','display_visual_verified','encoded_recording_or_optics_retested_after_resume','acoustics_retested_after_resume','physical_failed_reset_fault_injected']:
            self.assertIs(self.report[k],False)
        self.assertIs(self.report['old_hard_freeze_unresolved'],True)
        self.assertIs(self.report['failed_reset_dma_quiescence_unresolved'],True)


if __name__=='__main__':
    unittest.main()
