"""Extract real open/release and vb2 release helpers; model PM/CSS and queue stop."""
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2]
fops = (root / 'drivers/staging/media/atomisp/pci/atomisp_fops.c').read_text()
vb2 = (root / 'drivers/media/common/videobuf2/videobuf2-v4l2.c').read_text()

def function(text, signature):
    start = text.index(signature)
    pos = text.index('{', start)
    depth = 1
    end = pos + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

code = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct mutex { pthread_mutex_t lock; };
static void mutex_lock(struct mutex *m) { assert(!pthread_mutex_lock(&m->lock)); }
static void mutex_unlock(struct mutex *m) { assert(!pthread_mutex_unlock(&m->lock)); }
struct atomisp_device { void *dev; struct mutex mutex; unsigned int input_cnt; };
struct atomisp_sub_device { unsigned int input_curr; int state; };
struct vb2_queue { struct mutex *lock; void *owner; bool streaming; unsigned int buffers; };
struct v4l2_device { void *dev; };
struct atomisp_video_pipe { struct atomisp_sub_device *asd; unsigned int users; };
struct video_device { struct atomisp_device *isp; struct atomisp_video_pipe *pipe;
    struct v4l2_device *v4l2_dev; struct vb2_queue *queue; struct mutex *lock; const char *name; };
struct file { struct video_device *vdev; void *private_data; };
struct v4l2_subdev_fh { int vfh; };
static struct atomisp_device isp = {.mutex = {PTHREAD_MUTEX_INITIALIZER}, .input_cnt = 2};
static struct mutex queue_lock = {PTHREAD_MUTEX_INITIALIZER};
static struct atomisp_sub_device asd;
static struct atomisp_video_pipe pipe_ = {.asd = &asd};
static struct v4l2_device v4l2dev;
static struct vb2_queue queue = {.lock = &queue_lock};
static struct video_device vdev = {.isp = &isp, .pipe = &pipe_, .v4l2_dev = &v4l2dev,
    .queue = &queue, .lock = &isp.mutex, .name = "host-model"};
static int pm_refs, pm_gets, pm_puts, init_dev, init_subdev, free_stats, free_internal,
    sensor_off, destroy_streams, queue_releases, stream_stops;
static int injected_pm_error, injected_fh_error;
static int fh_allocated;
static struct video_device *video_devdata(struct file *f) { return f->vdev; }
static struct atomisp_device *video_get_drvdata(struct video_device *v) { return v->isp; }
static struct atomisp_video_pipe *atomisp_to_video_pipe(struct video_device *v) { return v->pipe; }
#define dev_dbg(...) do {} while (0)
#define dev_err(...) do {} while (0)
static int v4l2_fh_open(struct file *f) {
    if (injected_fh_error) return injected_fh_error;
    f->private_data = malloc(1); assert(f->private_data);
    __atomic_add_fetch(&fh_allocated, 1, __ATOMIC_SEQ_CST); return 0;
}
static int v4l2_fh_release(struct file *f) {
    assert(f->private_data); free(f->private_data); f->private_data = NULL;
    __atomic_sub_fetch(&fh_allocated, 1, __ATOMIC_SEQ_CST); return 0;
}
static void v4l2_fh_init(int *fh, struct video_device *v) { (void)fh; (void)v; }
static int pm_runtime_resume_and_get(void *dev) {
    (void)dev; if (injected_pm_error) return injected_pm_error;
    ++pm_gets; assert(++pm_refs == 1); return 0;
}
static int pm_runtime_put_sync(void *dev) { (void)dev; ++pm_puts; assert(--pm_refs == 0); return 0; }
static void atomisp_dev_init_struct(struct atomisp_device *p) { (void)p; ++init_dev; }
static void atomisp_subdev_init_struct(struct atomisp_sub_device *p) { ++init_subdev; p->state = 7; }
static void atomisp_css_free_stat_buffers(struct atomisp_sub_device *p) { (void)p; ++free_stats; }
static void atomisp_free_internal_buffers(struct atomisp_sub_device *p) { (void)p; ++free_internal; }
static void atomisp_s_sensor_power(struct atomisp_device *p, unsigned int in, int on) {
    (void)p; (void)in; assert(!on); ++sensor_off;
}
static void atomisp_destroy_pipes_stream(struct atomisp_sub_device *p) { ++destroy_streams; p->state = 0; }
static void vb2_queue_release(struct vb2_queue *q) {
    ++queue_releases;
    if (q->streaming) { ++stream_stops; q->streaming = false; }
    q->buffers = 0;
}
'''
code += function(vb2, 'int _vb2_fop_release(') + '\n'
code += function(vb2, 'int vb2_fop_release(') + '\n'
code += function(fops, 'static int atomisp_open(') + '\n'
code += function(fops, 'static int atomisp_release(') + '\n'
code += r'''
static void own_queue(struct file *f, bool streaming) {
    mutex_lock(&queue_lock);
    assert(!queue.owner); queue.owner = f->private_data;
    queue.buffers = 8; queue.streaming = streaming;
    mutex_unlock(&queue_lock);
}
static void check_quiescent(void) {
    assert(!pipe_.users && !pm_refs && !fh_allocated && !queue.owner && !queue.streaming);
    assert(pm_gets == pm_puts && pm_gets == init_dev && init_dev == init_subdev);
    assert(pm_puts == free_stats && free_stats == free_internal);
    assert(pm_puts == sensor_off && sensor_off == destroy_streams);
}
static void *worker(void *arg) {
    (void)arg;
    for (int i = 0; i < 2000; ++i) {
        struct file f = {.vdev = &vdev};
        assert(!atomisp_open(&f));
        assert(!atomisp_release(&f));
    }
    return NULL;
}
int main(void) {
    struct file a = {.vdev = &vdev}, b = {.vdev = &vdev}, c = {.vdev = &vdev};
    injected_fh_error = -ENOMEM;
    assert(atomisp_open(&a) == -ENOMEM); injected_fh_error = 0; check_quiescent();
    isp.input_cnt = 0;
    assert(atomisp_open(&a) == -EINVAL); isp.input_cnt = 2; check_quiescent();
    injected_pm_error = -EIO;
    assert(atomisp_open(&a) == -EIO); injected_pm_error = 0; check_quiescent();
    assert(!atomisp_open(&a));
    int result = atomisp_open(&b);
    if (result) {
        atomisp_release(&a);
        fprintf(stderr, "second open returned %d; expected 0\n", result);
        return 1;
    }
    assert(pipe_.users == 2 && pm_refs == 1 && init_dev == 1);
    // Observer close must not touch a queue owned by another live handle.
    own_queue(&a, true); asd.state = 123;
    int stats = free_stats, released = queue_releases, stops = stream_stops;
    assert(!atomisp_release(&b));
    assert(pipe_.users == 1 && pm_refs == 1 && queue.streaming && queue.buffers == 8);
    assert(queue_releases == released && stream_stops == stops && free_stats == stats && asd.state == 123);
    assert(!atomisp_open(&b));
    assert(!atomisp_open(&c));
    assert(asd.state == 123 && pm_refs == 1);
    // Owner close stops only its queue; remaining handles retain hardware state.
    assert(!atomisp_release(&a));
    assert(pipe_.users == 2 && pm_refs == 1 && !queue.owner && !queue.streaming);
    assert(stream_stops == stops + 1 && free_stats == stats && asd.state == 123);
    own_queue(&b, true);
    assert(!atomisp_release(&c));
    assert(queue.streaming && pm_refs == 1);
    assert(!atomisp_release(&b)); check_quiescent();
    // Repeat owner-first and observer-first closure across PM lifetime resets.
    for (int i = 0; i < 2000; ++i) {
        assert(!atomisp_open(&a)); assert(!atomisp_open(&b));
        assert(!atomisp_open(&c)); own_queue(&b, i % 2);
        assert(!atomisp_release(i % 2 ? &b : &a));
        if (i % 2) { own_queue(&a, true); assert(!atomisp_release(&c)); assert(!atomisp_release(&a)); }
        else { assert(queue.owner == b.private_data); assert(!atomisp_release(&c)); assert(!atomisp_release(&b)); }
        check_quiescent();
    }
    pthread_t threads[8];
    for (int i = 0; i < 8; ++i) assert(!pthread_create(&threads[i], NULL, worker, NULL));
    for (int i = 0; i < 8; ++i) assert(!pthread_join(threads[i], NULL));
    check_quiescent();
    printf("PASS injected failures, queue-owner takeover, 2000 closure cycles, 16000 concurrent opens/closes\n");
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-multiopen-host-') as temp:
    src = pathlib.Path(temp) / 'test.c'
    exe = pathlib.Path(temp) / 'test'
    src.write_text(code)
    subprocess.run(['clang', '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-variable',
                    '-Wno-unused-function', '-Werror', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-pthread', str(src), '-o', str(exe)], check=True)
    raise SystemExit(subprocess.run([str(exe)]).returncode)
