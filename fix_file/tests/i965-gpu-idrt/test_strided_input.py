from copy import deepcopy
import hashlib,unittest
from strided_input import fingerprint,layout_spans,verify
def layout(padded=True):return dict(format='NV12',width=1920,height=1080,n_planes=2,offsets=[0,2088960 if padded else 2073600],strides=[1920,1920])
def fixture():
 return [dict(index=i,PTS_ns=i*1000000000//30,duration_ns=(i+1)*1000000000//30-i*1000000000//30,visible_bytes=3110400,storage_bytes=3133440,visible_SHA256=hashlib.sha256(str(i).encode()).hexdigest(),storage_SHA256=hashlib.sha256(('storage'+str(i)).encode()).hexdigest(),layout=layout()) for i in range(180)]
class Strided(unittest.TestCase):
 def test_real_hardware_layout(self):self.assertEqual(layout_spans(layout(),3133440),[(0,2073600,1080,1920),(2088960,3125760,540,1920)])
 def test_packed_layout_supported(self):self.assertEqual(layout_spans(layout(False),3110400)[1][1],3110400)
 def test_padding_not_visible_pixels_but_still_hashed(self):
  a=bytearray(3133440);b=bytearray(a);b[2073600]=1;b[-1]=2;x=fingerprint(a,layout());y=fingerprint(b,layout());self.assertEqual(x['visible_SHA256'],y['visible_SHA256']);self.assertNotEqual(x['storage_SHA256'],y['storage_SHA256']);self.assertEqual(b[2073600],1)
 def test_active_last_Y_byte_observed(self):
  a=bytearray(3133440);before=fingerprint(a,layout());a[2073599]=1;self.assertNotEqual(before['visible_SHA256'],fingerprint(a,layout())['visible_SHA256'])
 def test_active_first_UV_byte_observed(self):
  a=bytearray(3133440);before=fingerprint(a,layout());a[2088960]=1;self.assertNotEqual(before['visible_SHA256'],fingerprint(a,layout())['visible_SHA256'])
 def test_active_last_UV_byte_observed(self):
  a=bytearray(3133440);before=fingerprint(a,layout());a[3125759]=1;self.assertNotEqual(before['visible_SHA256'],fingerprint(a,layout())['visible_SHA256'])
 def reject_layout(self,change,size=3133440):
  x=layout();change(x)
  with self.assertRaises(ValueError):layout_spans(x,size)
 def test_lower_resolution_rejected(self):self.reject_layout(lambda x:x.update(width=1280,height=720))
 def test_wrong_format(self):self.reject_layout(lambda x:x.update(format='I420'))
 def test_wrong_planes(self):self.reject_layout(lambda x:x.update(n_planes=3))
 def test_overlap(self):self.reject_layout(lambda x:x.update(offsets=[0,2071680]))
 def test_negative_stride(self):self.reject_layout(lambda x:x.update(strides=[-1920,1920]))
 def test_too_small_stride(self):self.reject_layout(lambda x:x.update(strides=[1918,1920]))
 def test_out_of_bounds(self):self.reject_layout(lambda x:x.update(offsets=[0,2088960+20000]))
 def test_uv_alignment(self):self.reject_layout(lambda x:x.update(offsets=[0,2088961]))
 def test_bad_offset_count(self):self.reject_layout(lambda x:x.update(offsets=[0]))
 def test_boolean_stride(self):self.reject_layout(lambda x:x.update(strides=[True,1920]))
 def test_boolean_width(self):self.reject_layout(lambda x:x.update(width=True))
 def test_bounded_allocation(self):self.reject_layout(lambda x:None,size=16*1024**2)
 def test_under_native_allocation(self):self.reject_layout(lambda x:None,size=3110399)
 def test_valid_dynamic_rows(self):self.assertEqual(verify(fixture())['unique_visible_hashes'],180)
 def reject_rows(self,change):
  x=fixture();change(x)
  with self.assertRaises(ValueError):verify(x)
 def test_missing_frame(self):self.reject_rows(lambda x:x.pop())
 def test_extra_frame(self):self.reject_rows(lambda x:x.append(deepcopy(x[-1])))
 def test_reordered_frames(self):self.reject_rows(lambda x:x.reverse())
 def test_retimed_PTS(self):self.reject_rows(lambda x:x[5].update(PTS_ns=x[5]['PTS_ns']+1))
 def test_short_visible_payload(self):self.reject_rows(lambda x:x[5].update(visible_bytes=1036800))
 def test_malformed_hash(self):self.reject_rows(lambda x:x[5].update(visible_SHA256='f'*63))
 def test_static_frames_rejected(self):self.reject_rows(lambda x:[row.update(visible_SHA256='a'*64) for row in x])
 def test_insufficient_motion_rejected(self):self.reject_rows(lambda x:[row.update(visible_SHA256=hashlib.sha256(str(i%89).encode()).hexdigest()) for i,row in enumerate(x)])
 def test_full_storage_identity_separate(self):
  a=fixture();b=fixture();b[0]['storage_SHA256']='a'*64;aa=verify(a);bb=verify(b);self.assertEqual(aa['ordered_visible_rows_SHA256'],bb['ordered_visible_rows_SHA256']);self.assertEqual(aa['layout_sequence_SHA256'],bb['layout_sequence_SHA256']);self.assertNotEqual(aa['ordered_storage_rows_SHA256'],bb['ordered_storage_rows_SHA256'])
 def test_visible_change_is_not_hidden(self):
  a=fixture();b=fixture();b[5]['visible_SHA256']='a'*64;self.assertNotEqual(verify(a)['ordered_visible_rows_SHA256'],verify(b)['ordered_visible_rows_SHA256'])
 def test_live_clock_origin_preserved_but_not_false_pixel_difference(self):
  a=fixture();b=fixture()
  for row in b:row['PTS_ns']+=54146456
  aa=verify(a);bb=verify(b);self.assertEqual(aa['ordered_visible_rows_SHA256'],bb['ordered_visible_rows_SHA256']);self.assertEqual(bb['first_input_PTS_ns'],54146456);self.assertTrue(bb['original_PTS_and_duration_verified'])
 def test_nonuniform_origin_shift_rejected(self):self.reject_rows(lambda x:x[5].update(PTS_ns=x[5]['PTS_ns']+54146456))
 def test_invalid_clock_none_rejected(self):self.reject_rows(lambda x:x[0].update(PTS_ns=(1<<64)-1))
if __name__=='__main__':unittest.main()
