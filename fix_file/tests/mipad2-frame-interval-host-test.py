#!/usr/bin/env python3
"""Compile actual sensor pad-op functions with control/locking stubs.

Checks interval arithmetic, limits, reset requests, validation and errno
propagation. It does not test sensor registers, runtime PM or ISP streaming.
"""
import json
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if not (ROOT / 'drivers').exists():
    ROOT = pathlib.Path('/root/linux_latte-6.14-integrated')

def functions(name):
    s = (ROOT / f'drivers/media/i2c/{name}.c').read_text()
    start = s.index(f'static int {name}_get_frame_interval(')
    end = s.index('\nstatic ', s.index(f'static int {name}_set_frame_interval(', start) + 1)
    return s[start:end]

macros = []
for filename, names in [('ov5693', ['OV5693_FIXED_PPL', 'OV5693_PIXEL_RATE']),
                        ('t4ka3', ['T4KA3_PIXELS_PER_LINE', 'T4KA3_LINES_PER_FRAME_30FPS', 'T4KA3_FPS', 'T4KA3_PIXEL_RATE'])]:
    s = (ROOT / f'drivers/media/i2c/{filename}.c').read_text()
    for name in names:
        lines = s.splitlines()
        index = next(i for i, line in enumerate(lines)
                     if re.match(r'^#define ' + name + r'[ \t]', line))
        definition = lines[index]
        while lines[index].endswith('\\'):
            index += 1
            definition += '\n' + lines[index]
        macros.append(definition)

PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <linux/v4l2-subdev.h>
typedef uint64_t u64;
struct mutex { int depth; };
static void mutex_lock(struct mutex *m) { assert(!m->depth); m->depth++; }
static void mutex_unlock(struct mutex *m) { assert(m->depth == 1); m->depth--; }
static u64 div64_u64(u64 a, u64 b) { assert(b); return a / b; }
static unsigned int gcd(unsigned int a, unsigned int b) {
    while (b) { unsigned int tmp = a % b; a = b; b = tmp; } return a;
}
#define clamp_t(type, a, b, c) ((type)(a) < (type)(b) ? (type)(b) : ((type)(a) > (type)(c) ? (type)(c) : (type)(a)))
struct v4l2_ctrl { int val; int64_t minimum, maximum, default_value; };
static int ctrl_error, ctrl_calls;
static int __v4l2_ctrl_s_ctrl(struct v4l2_ctrl *c, int val) {
    ctrl_calls++;
    if (ctrl_error) return ctrl_error;
    assert(val >= c->minimum && val <= c->maximum);
    c->val = val; return 0;
}
struct format { unsigned int height; };
struct v4l2_subdev_state { struct format format; };
struct v4l2_subdev { void *private; };
struct ov5693_device { struct mutex lock; struct { struct format format; } mode;
    struct { struct v4l2_ctrl *vblank; } ctrls; };
struct t4ka3_data { struct mutex lock; struct { struct v4l2_ctrl *vblank; } ctrls; };
static struct ov5693_device *to_ov5693_sensor(struct v4l2_subdev *sd) { return sd->private; }
static struct t4ka3_data *to_t4ka3_sensor(struct v4l2_subdev *sd) { return sd->private; }
static struct format *v4l2_subdev_state_get_format(struct v4l2_subdev_state *s, unsigned int pad) { assert(!pad); return &s->format; }
'''
TEST = r'''
static unsigned int count;
typedef int (*interval_op)(struct v4l2_subdev *, struct v4l2_subdev_state *, struct v4l2_subdev_frame_interval *);
static void exercise(interval_op set, interval_op get, struct v4l2_subdev *sd,
                     struct v4l2_subdev_state *state, struct v4l2_ctrl *blank,
                     unsigned int height, unsigned int rate, unsigned int ppl) {
    uint32_t inputs[][2] = {{0,0},{0,1},{1,0},{1,30},{1,60},{1,1},
        {UINT32_MAX,1},{1,UINT32_MAX},{UINT32_MAX,UINT32_MAX},
        {1,16777216},{UINT32_MAX,16777216},{17,23}};
    uint32_t seed = 42;
    for (unsigned int i = 0; i < 20012; i++) {
        uint32_t n, d;
        if (i < 12) { n = inputs[i][0]; d = inputs[i][1]; }
        else { seed = seed * 1664525u + 1013904223u; n = seed;
               seed = seed * 1664525u + 1013904223u; d = seed; }
        uint64_t lines;
        if (!n || !d) lines = height + blank->default_value;
        else {
            __uint128_t a = (__uint128_t)rate * n, b = (__uint128_t)ppl * d;
            lines = (a + b/2) / b;
            if (lines < height + blank->minimum) lines = height + blank->minimum;
            if (lines > height + blank->maximum) lines = height + blank->maximum;
        }
        struct v4l2_subdev_frame_interval fi = {.which=V4L2_SUBDEV_FORMAT_ACTIVE, .interval={n,d}};
        assert(!set(sd,state,&fi));
        assert(blank->val == (int)(lines-height));
        assert(fi.interval.numerator && fi.interval.denominator);
        assert((uint64_t)fi.interval.numerator * rate ==
               (uint64_t)fi.interval.denominator * lines * ppl);
        assert(gcd(fi.interval.numerator,fi.interval.denominator)==1);
        struct v4l2_subdev_frame_interval actual = {.which=V4L2_SUBDEV_FORMAT_ACTIVE};
        assert(!get(sd,state,&actual));
        assert(actual.interval.numerator == fi.interval.numerator);
        assert(actual.interval.denominator == fi.interval.denominator);
        count++;
    }
    for (unsigned int i=0;i<2;i++) {
        struct v4l2_subdev_frame_interval fi = {.which=V4L2_SUBDEV_FORMAT_ACTIVE, .interval={1,30}};
        if (i) fi.pad=1; else fi.which=V4L2_SUBDEV_FORMAT_TRY;
        int calls=ctrl_calls, saved=blank->val;
        assert(set(sd,state,&fi)==-EINVAL);
        assert(get(sd,state,&fi)==-EINVAL);
        assert(ctrl_calls==calls && blank->val==saved);
        count++;
    }
    struct v4l2_subdev_frame_interval fi = {.which=V4L2_SUBDEV_FORMAT_ACTIVE, .interval={1,30}};
    int saved=blank->val;
    ctrl_error=-EIO;
    assert(set(sd,state,&fi)==-EIO && blank->val==saved);
    ctrl_error=0;
    count++;
}
int main(void) {
    unsigned int heights[]={2,720,1230,2460};
    for (unsigned int i=0;i<4;i++) {
        struct v4l2_ctrl blank={.minimum=4,.maximum=65535-heights[i],.default_value=2492-heights[i]};
        struct v4l2_subdev_state state={.format={heights[i]}};
        struct ov5693_device ov={.mode={.format={heights[i]}},.ctrls={&blank}};
        struct v4l2_subdev sd={&ov};
        exercise(ov5693_set_frame_interval,ov5693_get_frame_interval,&sd,&state,&blank,heights[i],OV5693_PIXEL_RATE,OV5693_FIXED_PPL);
        assert(ov.lock.depth==0);
        struct t4ka3_data t4={.ctrls={&blank}};
        sd.private=&t4;
        exercise(t4ka3_set_frame_interval,t4ka3_get_frame_interval,&sd,&state,&blank,heights[i],T4KA3_PIXEL_RATE,T4KA3_PIXELS_PER_LINE);
    }
    printf("PASS %u interval cases; real pad-op source, stubbed controls/locks\n",count);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-frame-interval-test-') as temp:
    p = pathlib.Path(temp)
    (p / 'test.c').write_text(PRELUDE + '\n' + '\n'.join(macros) + '\n' + functions('ov5693') + functions('t4ka3') + TEST)
    subprocess.run(['gcc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-fsanitize=undefined,address', '-fno-sanitize-recover=all', str(p / 'test.c'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
