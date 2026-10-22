import fcntl,json,os,pathlib,re,struct,subprocess,time
BASE=pathlib.Path('/var/lib/mipad2-kernel/6.14.0-mipad2-integrated-r24')
assert os.geteuid()==0
assert subprocess.check_output(['uname','-r'],text=True).strip()==BASE.name
def run(a,timeout=70):
    p=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
    return {'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def ctl(n,c,v=None):
    with open(n,'rb+',buffering=0) as f:
        b=bytearray(struct.pack('Ii',c,0 if v is None else v));fcntl.ioctl(f,0xc008561b if v is None else 0xc008561c,b,True);return struct.unpack('Ii',b)[1]
def controls(node,index=None):
    import errno
    CID_VBLANK=0x009e0901
    NEXT_CTRL=0x80000000
    QUERYCTRL=0xc0445624
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
def shape(n):
    p=run(['v4l2-ctl','-d',n,'--get-subdev-fmt=pad=0']);assert p['code']==0,p
    w,h=map(int,re.search(r'Width/Height\s*:\s*(\d+)/(\d+)',p['stdout']).groups())
    code=re.search(r'Mediabus Code\s*:\s*(0x[0-9a-fA-F]+)',p['stdout']).group(1)
    sel=run(['v4l2-ctl','-d',n,'--get-subdev-selection=pad=0,target=crop'])
    match=re.search(r'Left (-?\d+), Top (-?\d+), Width (\d+), Height (\d+)',sel['stdout'])
    return {'width':w,'height':h,'code':code,'crop':list(map(int,match.groups())) if match else None}
names={p.name:(p/'name').read_text().strip() for p in pathlib.Path('/sys/class/video4linux').glob('v4l-subdev*')}
debug=pathlib.Path('/sys/kernel/debug/dynamic_debug/control')
lines=[]
before_flags=[l for l in debug.read_text().splitlines() if any('atomisp_cmd.c:'+str(n)+' ' in l for n in lines)]
assert len(before_flags)==len(lines) and all(' =_ ' in l for l in before_flags),before_flags
report={'kernel':BASE.name,'debug_before':before_flags,'cases':[],'scope':'r24 cached-format reuse without S_FMT and ordinary STREAMOFF/ON plus strict takeover'}
log_before=run(['dmesg'])['stdout']
try:
    for line in lines:debug.write_text(f'file atomisp_cmd.c line {line} +p\n')
    for index,prefix in [(0,'ov5693 '),(1,'t4ka3 ')]:
        assert subprocess.run(['fuser','/dev/video0'],capture_output=True).returncode==1
        node='/dev/'+next(n for n,v in names.items() if v.startswith(prefix))
        p=run(['v4l2-ctl','-d','/dev/video0',f'--set-input={index}']);assert p['code']==0,p
        assert prefix.strip() in p['stdout'], 'Video input does not match sensor subdev: '+repr(p)
        original_shape=shape(node);original_controls=controls(node,index)
        case={'input':index,'node':node,'original_shape':original_shape,'original_controls':original_controls}
        report['cases'].append(case)
        try:
            p=run(['v4l2-ctl','-d','/dev/video0','--set-fmt-video=width=1280,height=720,pixelformat=YU12']);assert p['code']==0,p
            case['cadence']=[]
            for rate in [30,15]:
                setting=run(['v4l2-ctl','-d','/dev/video0',f'--set-parm={rate}']);assert setting['code']==0,setting
                capture=run(['/var/tmp/mipad2-r24-cadence-enum-device-test','/dev/video0',str(rate),node])
                phases={}
                for phase,sec,usec in re.findall(r'([a-z-]+) frame=\d+ bytes=\d+ timestamp=(\d+)\.(\d+)',capture['stdout']):
                    phases.setdefault(phase,[]).append(int(sec)+int(usec)*1e-6)
                measured={phase:(len(ts)-1)/(ts[-1]-ts[0]) for phase,ts in phases.items() if len(ts)>1}
                case['cadence'].append({'requested_fps':rate,'setting':setting,'capture':capture,'measured_fps':measured,'period_gate':len(measured)==4 and all(abs(fps-rate)/rate<0.01 for fps in measured.values())})
            case['streamparm_correct_node']=run(['/var/tmp/mipad2-streamparm-abi-test-r24','/dev/video0',node,'/dev/'+next(n for n,v in names.items() if v=='Atom ISP')])
        finally:
            errors=[]
            s=original_shape
            if s['crop'] is not None and shape(node)['crop']!=s['crop']:
                x,y,w,h=s['crop'];p=run(['v4l2-ctl','-d',node,f'--set-subdev-selection=pad=0,target=crop,left={x},top={y},width={w},height={h}'])
                if p['code']:errors.append(p)
            p=run(['v4l2-ctl','-d',node,f"--set-subdev-fmt=pad=0,width={s['width']},height={s['height']},code={s['code']}"])
            if p['code']:errors.append(p)
            for c,v in original_controls.items():
                try:ctl(node,c,v);assert ctl(node,c)==v
                except Exception as e:errors.append({'control':c,'error':repr(e)})
            case['shape_after']=shape(node);case['controls_after']=controls(node,index);case['restore_errors']=errors
finally:
    for line in lines:debug.write_text(f'file atomisp_cmd.c line {line} -p\n')
    report['debug_after']=[l for l in debug.read_text().splitlines() if any('atomisp_cmd.c:'+str(n)+' ' in l for n in lines)]
    report['debug_restored']=report['debug_after']==before_flags
    after=run(['dmesg'])['stdout'];report['new_dmesg']=after[len(log_before):] if after.startswith(log_before) else after
    report['restore_input']=run(['v4l2-ctl','-d','/dev/video0','--set-input=0'])
    (BASE/'r24-cadence-no-sfmt-restart.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

assert all(not c["restore_errors"] and c["original_shape"]==c["shape_after"] and c["original_controls"]==c["controls_after"] and c["streamparm_correct_node"]["code"]==0 and all(t["capture"]["code"]==0 and t["period_gate"] for t in c["cadence"]) for c in report["cases"]), "Cadence gate failed; inspect saved report"
assert report["debug_restored"]
