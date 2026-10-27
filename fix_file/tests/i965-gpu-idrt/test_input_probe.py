# SPDX-License-Identifier: MIT
from pathlib import Path
import argparse,ctypes,hashlib,json,sys,unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from strided_input import fingerprint
LIB=None
class Layout(ctypes.Structure):
 _fields_=[('width',ctypes.c_uint32),('height',ctypes.c_uint32),('planes',ctypes.c_uint32),('nv12',ctypes.c_uint32),('offset',ctypes.c_uint64*2),('stride',ctypes.c_int32*2)]
class Native(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.lib=ctypes.CDLL(str(LIB));cls.lib.mp2_nv12_hash.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.POINTER(Layout),ctypes.c_void_p,ctypes.c_void_p];cls.lib.mp2_nv12_hash.restype=ctypes.c_int
 def test_real_C_fingerprint_matches_independent_Python_32_layouts(self):
  for i in range(32):
   with self.subTest(layout=i):
    strides=[1920+32*(i%3),1920+64*((i+1)%3)];offsets=[64*(i%4),0];offsets[1]=(offsets[0]+1080*strides[0]+64*(i%5)+63)&~63;size=offsets[1]+540*strides[1]+64*(i%4)
    source=(bytes(range(256))*(size//256+1))[:size];buf=ctypes.create_string_buffer(source);a=ctypes.create_string_buffer(65);b=ctypes.create_string_buffer(65);layout=Layout(1920,1080,2,1,(ctypes.c_uint64*2)(*offsets),(ctypes.c_int32*2)(*strides))
    self.assertEqual(self.lib.mp2_nv12_hash(buf,size,ctypes.byref(layout),a,b),1);gold=fingerprint(source,dict(width=1920,height=1080,n_planes=2,format='NV12',offsets=offsets,strides=strides));self.assertEqual(a.value.decode(),gold['visible_SHA256']);self.assertEqual(b.value.decode(),gold['storage_SHA256']);self.assertEqual(buf.raw[:-1],source);self.assertEqual(buf.raw[-1],0)
 def test_invalid_layouts_rejected_before_any_read(self):
  # NULL input is rejected; non-NULL one-byte sentinel must never be read for invalid layouts.
  data=ctypes.create_string_buffer(b'x');a=ctypes.create_string_buffer(65);b=ctypes.create_string_buffer(65)
  cases=[dict(width=1280),dict(height=720),dict(planes=3),dict(nv12=0),dict(stride=(ctypes.c_int32*2)(1918,1920)),dict(stride=(ctypes.c_int32*2)(-1920,1920)),dict(offset=(ctypes.c_uint64*2)(0,2071680)),dict(offset=(ctypes.c_uint64*2)(0,2088961)),dict(offset=(ctypes.c_uint64*2)(0,3133440))]
  for changes in cases:
   layout=Layout(1920,1080,2,1,(ctypes.c_uint64*2)(0,2088960),(ctypes.c_int32*2)(1920,1920))
   for name,value in changes.items():setattr(layout,name,value)
   self.assertEqual(self.lib.mp2_nv12_hash(data,3133440,ctypes.byref(layout),a,b),0)
  layout=Layout(1920,1080,2,1,(ctypes.c_uint64*2)(0,2088960),(ctypes.c_int32*2)(1920,1920))
  for size in [0,3110399,16*1024**2]:self.assertEqual(self.lib.mp2_nv12_hash(data,size,ctypes.byref(layout),a,b),0)
  self.assertEqual(self.lib.mp2_nv12_hash(None,3133440,ctypes.byref(layout),a,b),0)
 def test_owned_GObject_capsule_attach_NULL_finish_without_streaming(self):
  import gi
  gi.require_version('Gst','1.0');from gi.repository import Gst
  Gst.init(None);pipeline=Gst.parse_launch('videotestsrc ! identity name=encoder ! fakesink')
  getname=ctypes.pythonapi.PyCapsule_GetName;getname.argtypes=[ctypes.py_object];getname.restype=ctypes.c_char_p
  getptr=ctypes.pythonapi.PyCapsule_GetPointer;getptr.argtypes=[ctypes.py_object,ctypes.c_char_p];getptr.restype=ctypes.c_void_p
  capsule=pipeline.__gpointer__;ptr=getptr(capsule,getname(capsule));self.assertTrue(ptr)
  self.lib.mp2_probe_attach.argtypes=[ctypes.c_void_p];self.lib.mp2_probe_attach.restype=ctypes.c_void_p;self.lib.mp2_probe_finish.argtypes=[ctypes.c_void_p];self.lib.mp2_probe_finish.restype=ctypes.c_void_p;self.lib.mp2_probe_free_string.argtypes=[ctypes.c_void_p]
  self.assertFalse(self.lib.mp2_probe_attach(None));handle=self.lib.mp2_probe_attach(ptr);self.assertTrue(handle);data=self.lib.mp2_probe_finish(handle);self.assertTrue(data)
  try:r=json.loads(ctypes.string_at(data))
  finally:self.lib.mp2_probe_free_string(data)
  self.assertEqual(r['rows'],[]);self.assertEqual(r['count'],0);self.assertEqual(r['error'],0);self.assertEqual(pipeline.current_state,Gst.State.NULL)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--library',required=True,type=Path);LIB=p.parse_args().library
 raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Native)).wasSuccessful() else 1)
