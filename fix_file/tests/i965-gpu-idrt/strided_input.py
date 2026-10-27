# SPDX-License-Identifier: MIT
"""Read-only native NV12 fingerprint with explicit GstVideoMeta layout bounds."""
import hashlib,json,re
def require(value,message):
    if not value:raise ValueError(message)
def layout_spans(layout,storage_bytes):
    require(type(storage_bytes) is int and 3110400<=storage_bytes<16*1024**2,'Unexpected native input allocation size')
    require(type(layout) is dict and set(layout)=={'format','width','height','n_planes','offsets','strides'},'Explicit exact video layout required')
    require(layout['format']=='NV12' and type(layout['width']) is int and layout['width']==1920 and type(layout['height']) is int and layout['height']==1080,'Full native 1920x1080 NV12 image required')
    require(type(layout['n_planes']) is int and layout['n_planes']==2,'NV12 requires two declared planes')
    offsets=layout['offsets'];strides=layout['strides']
    require(type(offsets) is list and type(strides) is list and len(offsets)==len(strides)==2,'Exact two-plane offsets and strides required')
    require(all(type(x) is int and 0<=x<storage_bytes for x in offsets),'Invalid plane offset')
    require(all(type(x) is int and 1920<=x<=storage_bytes and x%2==0 for x in strides),'Invalid positive native NV12 stride')
    require(offsets[1]%2==0,'NV12 UV alignment required')
    spans=[(offsets[p],offsets[p]+(height-1)*strides[p]+1920,height,strides[p]) for p,height in enumerate([1080,540])]
    require(all(end<=storage_bytes for start,end,height,stride in spans),'Visible plane exceeds mapped allocation')
    require(spans[0][1]<=spans[1][0],'Y and UV plane spans overlap or are reordered')
    return spans
def fingerprint(storage,layout):
    view=memoryview(storage).cast('B');spans=layout_spans(layout,len(view));digest=hashlib.sha256();visible=0
    for start,end,height,stride in spans:
        for row in range(height):
            begin=start+row*stride;digest.update(view[begin:begin+1920]);visible+=1920
    require(visible==3110400,'All native visible Y/UV bytes required')
    return dict(layout=layout,visible_bytes=visible,storage_bytes=len(view),visible_SHA256=digest.hexdigest(),storage_SHA256=hashlib.sha256(view).hexdigest())
def verify(rows):
    require(type(rows) is list and len(rows)==180,'Exactly 180 observed input buffers required')
    origin=rows[0].get('PTS_ns') if type(rows[0]) is dict else None
    require(type(origin) is int and 0<=origin<(1<<64)-6000000001,'Valid original live-source clock origin required')
    visible=[];storage=[];layouts=[];hashes=[]
    for i,row in enumerate(rows):
        require(type(row) is dict and set(row)=={'index','PTS_ns','duration_ns','visible_bytes','storage_bytes','visible_SHA256','storage_SHA256','layout'},'Unexpected input row schema')
        require(type(row['index']) is int and row['index']==i,'Input ordering mismatch')
        pts=i*1000000000//30;duration=(i+1)*1000000000//30-pts
        require(type(row['PTS_ns']) is int and row['PTS_ns']==origin+pts and type(row['duration_ns']) is int and row['duration_ns']==duration,'Original 30/1 input timestamps and durations required')
        require(type(row['visible_bytes']) is int and row['visible_bytes']==3110400,'Full native visible NV12 payload required')
        layout_spans(row['layout'],row['storage_bytes'])
        for key in ['visible_SHA256','storage_SHA256']:require(type(row[key]) is str and re.fullmatch('[0-9a-f]{64}',row[key]) is not None,'Invalid payload hash')
        timing=dict(index=i,PTS_ns=pts,duration_ns=duration)
        visible.append(dict(**timing,SHA256=row['visible_SHA256']));storage.append(dict(**timing,SHA256=row['storage_SHA256']));layouts.append(dict(layout=row['layout'],storage_bytes=row['storage_bytes']));hashes.append(row['visible_SHA256'])
    require(len(set(hashes))>=90,'Moving visible-input diversity gate failed')
    sha=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(state='native-strided-moving-input-visible-pixel-observation-pass',buffers=180,size=[1920,1080],format='NV12',framerate='30/1',visible_bytes_per_buffer=3110400,unique_visible_hashes=len(set(hashes)),original_PTS_and_duration_verified=True,first_input_PTS_ns=origin,relative_timestamps_only_for_identity_comparison_not_buffer_rewriting=True,ordered_visible_rows_SHA256=sha(visible),ordered_storage_rows_SHA256=sha(storage),layout_sequence_SHA256=sha(layouts),distinct_layouts=[json.loads(x) for x in sorted({json.dumps(x,sort_keys=True) for x in layouts})],raw_pixels_persisted=False,padding_hashed_separately_not_zeroed_or_modified=True,encoder_input_only_not_sensor_or_MP4_payload_identity=True)
