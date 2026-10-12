import fcntl,json,os,pathlib,re,struct,subprocess,time
BASE=pathlib.Path('/var/lib/mipad2-kernel/6.14.0-mipad2-integrated-r17')
assert os.geteuid()==0
assert subprocess.check_output(['uname','-r'],text=True).strip()==BASE.name
def run(a,timeout=100):
    p=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
    return {'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def ctl(n,c,v=None):
    with open(n,'rb+',buffering=0) as f:
        b=bytearray(struct.pack('Ii',c,0 if v is None else v));fcntl.ioctl(f,0xc008561b if v is None else 0xc008561c,b,True);return struct.unpack('Ii',b)[1]
def controls(n,index):
    out={}
    for c in [0x009e0901,0x00980911,0x009e0903,0x0098090e,0x0098090f,0x009f0905]:
        try:out[c]=ctl(n,c)
        except OSError:assert c==0x009f0905 and index==1
    return out
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
report={'kernel':BASE.name,'debug_before':before_flags,'cases':[],'scope':'r17 video-node v4l2-compliance without streaming; both input snapshots restored'}
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
            case['compliance_no_stream']=run(['v4l2-compliance','-d','/dev/video0'],timeout=120)
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
    (BASE/'r17-compliance-no-stream.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'cases':[{k:v for k,v in c.items() if k not in ['original_controls','controls_after','original_shape','shape_after']} for c in report['cases']],'debug_restored':report['debug_restored']},indent=2))

assert report["debug_restored"] and all(not c["restore_errors"] and c["original_shape"]==c["shape_after"] and c["original_controls"]==c["controls_after"] for c in report["cases"]), "Compliance state restoration failed"
