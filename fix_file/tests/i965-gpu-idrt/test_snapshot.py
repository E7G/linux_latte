import struct,unittest
from snapshot import verify

def fixture(enabled=True,packets=3):
    b=bytearray(1888);struct.pack_into('<8sII6Q',b,0,b'MP2I9656',6,26,1234,1000000,2,0,0,0)
    for i in range(26):struct.pack_into('<8Q',b,64+64*i,packets,0,packets*10000,10000,packets*1000,1000,0,0)
    struct.pack_into('<4Q',b,1856,int(enabled),packets if enabled else 0,packets if enabled else 0,0);return b
def run(b,enabled=True,packets=3):return verify(bytes(b),expected_pid=1234,expected_enabled=enabled,expected_packets=packets)
def mutate(offset,value):
    b=fixture();struct.pack_into('<Q',b,offset,value);return b

class Snapshot(unittest.TestCase):
    def test_enabled_coverage(self):
        r=run(fixture());self.assertEqual(r['GPU_command_uploads'],3);self.assertFalse(r['GPU_completion_or_descriptor_contents_proven']);self.assertFalse(r['recording_cadence_or_OEM_parity_proven'])
    def test_disabled_same_binary_control(self):self.assertEqual(run(fixture(False),False)['GPU_command_uploads'],0)
    def test_old_size_rejected(self):
        with self.assertRaises(ValueError):run(fixture()[:1856])
    def test_trailing_data_rejected(self):
        with self.assertRaises(ValueError):run(fixture()+b'0')
    def test_old_magic_version_rejected(self):
        b=fixture();struct.pack_into('<8sI',b,0,b'MP2I9655',5)
        with self.assertRaises(ValueError):run(b)
    def test_unterminated_driver_rejected(self):
        with self.assertRaises(ValueError):run(mutate(40,1))
    def test_wrong_PID_rejected(self):
        with self.assertRaises(ValueError):run(mutate(16,5678))
    def test_uninitialized_counter_rejected(self):
        with self.assertRaises(ValueError):run(mutate(32,0))
    def test_both_experiments_rejected(self):
        with self.assertRaises(ValueError):run(mutate(48,1))
    def test_old_EARLY_preparation_rejected(self):
        with self.assertRaises(ValueError):run(mutate(56,1))
    def test_requested_flag_exact(self):
        with self.assertRaises(ValueError):run(fixture(),False)
    def test_CPU_fallback_not_accepted_as_GPU_coverage(self):
        b=fixture();struct.pack_into('<4Q',b,1856,1,3,2,1)
        with self.assertRaises(ValueError):run(b)
    def test_pending_preparation_not_ignored(self):
        with self.assertRaises(ValueError):run(mutate(1864,4))
    def test_disabled_control_GPU_commands_rejected(self):
        b=fixture(False);struct.pack_into('<4Q',b,1856,0,1,1,0)
        with self.assertRaises(ValueError):run(b,False)
    def test_every_phase_must_equal_packets(self):
        for i in range(26):
            with self.subTest(phase=i),self.assertRaises(ValueError):run(mutate(64+64*i,2))
    def test_phase_errors_not_ignored(self):
        with self.assertRaises(ValueError):run(mutate(72,1))
    def test_impossible_histogram_rejected(self):
        with self.assertRaises(ValueError):run(mutate(64+7*8,1))
    def test_no_recording_cannot_be_qualified(self):
        with self.assertRaises(ValueError):run(fixture(packets=0),packets=0)
    def test_enabled_must_be_boolean_not_integer(self):
        with self.assertRaises(ValueError):run(fixture(),1)
    def test_wrong_phase_count_rejected(self):
        b=fixture();struct.pack_into('<I',b,12,27)
        with self.assertRaises(ValueError):run(b)

if __name__=='__main__':unittest.main(verbosity=2)
