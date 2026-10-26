"""Portable ABI4 format/guard fixtures; no device, pixels, or GStreamer needed."""
from pathlib import Path
import struct
import tempfile
import unittest
import mipad2_frame_chain as d


def fixture():
    data=bytearray(d.DATA_START+16*128)
    d.HEADER.pack_into(data,0,b'MP2CTRL1',4,128,16,2,1,0,100,123)
    name=b'GstIdentity\tidentity\t/GstPipeline:test/GstIdentity:frame.GstPad:sink\0'
    data[64:64+len(name)]=name
    d.RECORD.pack_into(data,d.DATA_START,110,200,7,33333333,123,1,3,257,0,200,72,0,0,0,0,0,0,1)
    d.RECORD.pack_into(data,d.DATA_START+128,120,d.NONE,d.NONE,d.NONE,123,1,4,0,0,*([0]*8),2)
    return data


class FrameChainTests(unittest.TestCase):
    def decode(self,data):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'trace.bin';p.write_bytes(data);return d.read_trace(p)

    def test_metadata_factory_and_pair(self):
        t=self.decode(fixture());self.assertTrue(t['complete'])
        self.assertEqual(t['pads'][1]['factory'],'identity')
        calls=d.intervals(t);self.assertFalse(calls['unmatched_pre']);self.assertFalse(calls['unmatched_post'])
        r=calls['rows'][0]
        self.assertEqual((r['elapsed_ns'],r['pre_flow'],r['result'],r['aux'][:2]),(10,257,0,(200,72)))

    def test_overflow_not_complete(self):
        data=fixture();struct.pack_into('<Q',data,40,1)
        self.assertFalse(self.decode(data)['complete'])

    def test_uncommitted_not_complete(self):
        data=fixture();struct.pack_into('<Q',data,d.DATA_START+128+120,0)
        t=self.decode(data);self.assertFalse(t['complete']);self.assertEqual(t['incomplete'],1)
        self.assertTrue(d.intervals(t)['unmatched_pre'])

    def test_truncated_magic_version_recordsize_header(self):
        normal=fixture()
        variants=[normal[:30],normal[:-1],bytearray(normal),bytearray(normal),bytearray(normal)]
        variants[2][:8]=b'BADMAGIC';struct.pack_into('<I',variants[3],8,3);struct.pack_into('<I',variants[4],12,64)
        for data in variants:
            with self.subTest(length=len(data)),self.assertRaises(ValueError):self.decode(data)

    def test_invalid_dictionary(self):
        for name in [b'NoFactory\0',b'Type\t\t/path\0',b'\xff\tidentity\t/path\0',b'x'*512]:
            data=fixture();data[64:576]=bytes(512);data[64:64+len(name)]=name
            with self.subTest(name=name[:20]),self.assertRaises(ValueError):self.decode(data)

    def test_malformed_committed_record(self):
        for offset,fmt,value in [(32,'I',0),(40,'I',2),(44,'I',5),(0,'Q',99)]:
            data=fixture();struct.pack_into('<'+fmt,data,d.DATA_START+offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):self.decode(data)

    def test_full_segment_fields_and_invalid_rate(self):
        row=dict(operation='send-event',argument=17934,pre_flow=3,pts=100,duration=900,offset=5,aux=(3000,222,150,50,struct.unpack('<Q',struct.pack('<d',1.0))[0],struct.unpack('<Q',struct.pack('<d',1.0))[0],1,10000))
        s=d.segment(row);self.assertEqual((s['start'],s['base'],s['offset'],s['time'],s['seqnum']),(100,900,50,222,5))
        bad=dict(row,aux=(*row['aux'][:4],0,*row['aux'][5:]))
        with self.assertRaises(ValueError):d.segment(bad)


if __name__=='__main__':unittest.main()
