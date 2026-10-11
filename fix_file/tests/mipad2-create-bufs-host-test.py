#!/usr/bin/env python3
"""Actual queue source, CSS/control/locks stubbed; not hardware/DMA proof."""
from pathlib import Path
import subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
test=repo/'fix_file/tests/mipad2-queue-reconfigure-host-test.py'
namespace={'__file__':str(test)}
script=test.read_text();script=script[:script.index('with tempfile.TemporaryDirectory(')]
exec(compile(script,str(test),'exec'),namespace)
patched=namespace['s']
# Preserve and rerun all previous real-queue restoration tests before the new cases.
tests=namespace['tests'].replace('int main(void)', 'static int prior_tests(void)')
# main's implicit return does not apply to a renamed function.
tests=tests.replace('count);\n}', 'count);\n    return 0;\n}')
tests+=r'''
int main(void) {
    prior_tests();
    unsigned count=0;
    uint32_t seed=0x5693;
    for (unsigned n=0;n<100000;n++) {
        reset();css_ready=true;
        unsigned minimum=pipe_.pix.sizeimage;
        seed=seed*1664525u+1013904223u;
        unsigned incoming[]={0,1,2,minimum-1,minimum,minimum+1,minimum+1048576,UINT32_MAX,seed};
        for(unsigned p=1;p<=3;p++)for(unsigned i=0;i<9;i++) {
            reset();css_ready=true;
            unsigned planes=p,size=incoming[i],buffers=1;
            int ret=atomisp_queue_setup(&pipe_.vb_queue,&buffers,&planes,&size,NULL);
            bool valid=p==1 && incoming[i]>=minimum;
            assert(ret==(valid?0:-EINVAL));
            assert(planes==p && size==incoming[i] && buffers==1);
            assert(stats_calls==(valid?1u:0u) && !isp.mutex.depth && !format_calls);
            count++;
        }
    }
    printf("PASS %u CREATE_BUFS plane/size production cases; real function, stubs; NOT hardware proof\n",count);
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mp2-createbufs-prototype-') as d:
    p=Path(d);(p/'test.c').write_text(namespace['defines']+namespace['prelude']+patched+tests)
    subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
