"""Reusable next-version idle snapshot helper: all writable scalar controls.

Do not use partial literal lists for subdev compliance restoration. The caller
must keep camera clients closed and restore format/ranges before values.
"""
import errno,fcntl,struct

QUERYCTRL=0xc0445624
G_CTRL=0xc008561b
S_CTRL=0xc008561c
NEXT_CTRL=0x80000000
CID_VBLANK=0x009e0901

def ctl(node,cid,value=None):
    with open(node,'rb+',buffering=0) as f:
        buf=bytearray(struct.pack('Ii',cid,0 if value is None else value))
        fcntl.ioctl(f,G_CTRL if value is None else S_CTRL,buf,True)
        return struct.unpack('Ii',buf)[1]

def controls(node,index=None):
    del index  # Keep the former helper's call signature without fixed IDs.
    found={};cid=0
    assert struct.calcsize('II32siiiiIII')==68
    with open(node,'rb+',buffering=0) as f:
        for _ in range(256):
            buf=bytearray(struct.pack('II32siiiiIII',cid|NEXT_CTRL,0,b'',0,0,0,0,0,0,0))
            try:fcntl.ioctl(f,QUERYCTRL,buf,True)
            except OSError as e:
                if e.errno==errno.EINVAL:break
                raise
            current,kind,name,lo,hi,step,default,flags,_,_=struct.unpack('II32siiiiIII',buf)
            assert current>cid and not current&NEXT_CTRL
            cid=current
            if flags&4:continue  # Read-only controls/classes cannot be restored with S_CTRL.
            assert not flags&(8|0x80|0x100), ('Unsnapshotable mutable control',hex(cid),name,flags)
            assert kind in (1,2,3,8,9), ('Need an extended/compound snapshot',hex(cid),kind)
            found[cid]=ctl(node,cid)
        else:raise AssertionError('Unbounded control enumeration')
    # VBLANK changes exposure limits; restore it before EXPOSURE, irrespective
    # of the numeric ID ordering used by NEXT_CTRL.
    result={cid:found[cid] for cid in sorted(found,key=lambda x:(x!=CID_VBLANK,x))}
    for required in (0x009f0903,0x00980914,0x00980915):
        assert required in result, ('Missing test pattern/flip snapshot',hex(required))
    return result
