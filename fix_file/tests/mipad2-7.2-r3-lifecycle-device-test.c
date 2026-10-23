/* SPDX-License-Identifier: GPL-2.0 */
/* Destructive queue test on an otherwise idle AtomISP node. No S_FMT/S_PARM/
 * sensor control writes. Samples only buffer metadata, not optical content.
 * Per-frame records stay in RAM until all streams have stopped, then go to the
 * caller's new private CSV. The controller must stop after a hardware fault.
 */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>

#define FRAMES 120
#define PHASES 4
#define MAX_MAPS 32
struct mapping { void *address; size_t length; };
struct sample { unsigned phase, sequence, index, bytes; uint64_t timestamp_us; };
struct result {
 unsigned frames, gaps, errors, observer_busy_checks;
 uint64_t min_us, max_us, sum_us;
};
struct owner {
 int fd; bool streaming; unsigned count;
 struct mapping maps[MAX_MAPS]; struct v4l2_format format;
};
static struct sample records[FRAMES * PHASES];
static unsigned nrecords;
static int call(int fd, unsigned long op, void *arg)
{
 int ret;
 do { ret = ioctl(fd, op, arg); } while (ret < 0 && errno == EINTR);
 return ret;
}
static bool same_shape(const struct v4l2_format *a, const struct v4l2_format *b)
{
 return a->fmt.pix.width == b->fmt.pix.width && a->fmt.pix.height == b->fmt.pix.height &&
  a->fmt.pix.pixelformat == b->fmt.pix.pixelformat && a->fmt.pix.field == b->fmt.pix.field &&
  a->fmt.pix.sizeimage == b->fmt.pix.sizeimage && a->fmt.pix.bytesperline == b->fmt.pix.bytesperline;
}
static int shape_unchanged(struct owner *o)
{
 struct v4l2_format fmt = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
 if (call(o->fd, VIDIOC_G_FMT, &fmt) < 0) return -1;
 if (!same_shape(&fmt, &o->format)) { errno = EIO; return -1; }
 return 0;
}
static int prepare(struct owner *o, const char *node, unsigned expected_input)
{
 struct v4l2_capability cap = {0};
 struct v4l2_requestbuffers req = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
  .memory = V4L2_MEMORY_MMAP, .count = 4};
 unsigned input;
 o->fd = open(node, O_RDWR | O_NONBLOCK | O_CLOEXEC);
 if (o->fd < 0) return -1;
 if (call(o->fd, VIDIOC_QUERYCAP, &cap) < 0 || call(o->fd, VIDIOC_G_INPUT, &input) < 0) return -1;
 if (strcmp((char *)cap.driver, "atomisp") || input != expected_input) { errno = ENODEV; return -1; }
 o->format.type = req.type;
 if (call(o->fd, VIDIOC_G_FMT, &o->format) < 0) return -1;
 if (!o->format.fmt.pix.width || !o->format.fmt.pix.height ||
  !o->format.fmt.pix.sizeimage || o->format.fmt.pix.sizeimage > 24 * 1024 * 1024) { errno = EINVAL; return -1; }
 if (call(o->fd, VIDIOC_REQBUFS, &req) < 0) return -1;
 if (req.count < 4 || req.count > MAX_MAPS) { errno = EINVAL; return -1; }
 o->count = req.count;
 for (unsigned i = 0; i < req.count; i++) {
  struct v4l2_buffer b = {.type = req.type, .memory = req.memory, .index = i};
  if (call(o->fd, VIDIOC_QUERYBUF, &b) < 0) return -1;
  o->maps[i].length = b.length;
  o->maps[i].address = mmap(NULL, b.length, PROT_READ | PROT_WRITE, MAP_SHARED, o->fd, b.m.offset);
  if (o->maps[i].address == MAP_FAILED) return -1;
 }
 return shape_unchanged(o);
}
static int start(struct owner *o)
{
 for (unsigned i = 0; i < o->count; i++) {
  struct v4l2_buffer b = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
   .memory = V4L2_MEMORY_MMAP, .index = i};
  if (call(o->fd, VIDIOC_QBUF, &b) < 0) return -1;
 }
 enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
 if (call(o->fd, VIDIOC_STREAMON, &type) < 0) return -1;
 o->streaming = true;
 return shape_unchanged(o);
}
static int stop(struct owner *o)
{
 if (o->streaming) {
  enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (call(o->fd, VIDIOC_STREAMOFF, &type) < 0) return -1;
  o->streaming = false;
 }
 return 0;
}
static int cleanup(struct owner *o)
{
 int result = 0;
 if (o->fd < 0) return 0;
 if (stop(o) < 0) result = -1;
 for (unsigned i = 0; i < o->count; i++)
  if (o->maps[i].address && o->maps[i].address != MAP_FAILED) {
   if (munmap(o->maps[i].address, o->maps[i].length) < 0) result = -1;
   o->maps[i].address = NULL;
  }
 struct v4l2_requestbuffers req = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
 if (o->count && call(o->fd, VIDIOC_REQBUFS, &req) < 0) result = -1;
 if (close(o->fd) < 0) result = -1;
 o->fd = -1; o->count = 0;
 return result;
}
static int observer_checks(int fd, struct result *r)
{
 struct v4l2_requestbuffers req = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP, .count = 4};
 enum v4l2_buf_type type = req.type;
 struct v4l2_buffer q = {.type = req.type, .memory = req.memory};
 unsigned long ops[] = {VIDIOC_REQBUFS, VIDIOC_QBUF, VIDIOC_STREAMON, VIDIOC_STREAMOFF};
 void *args[] = {&req, &q, &type, &type};
 for (unsigned i = 0; i < sizeof(ops) / sizeof(ops[0]); i++) {
  errno = 0;
  if (call(fd, ops[i], args[i]) != -1 || errno != EBUSY) { errno = EIO; return -1; }
  r->observer_busy_checks++;
 }
 return 0;
}
static int capture(struct owner *o, const char *node, unsigned phase, struct result *r)
{
 int spectator = -1, result = -1;
 uint64_t previous = 0; unsigned sequence = 0;
 if (start(o) < 0) goto out;
 for (unsigned n = 0; n < FRAMES; n++) {
  if (n == 30) {
   spectator = open(node, O_RDWR | O_NONBLOCK | O_CLOEXEC);
   if (spectator < 0 || observer_checks(spectator, r) < 0) goto out;
  }
  if (n == 60) { if (close(spectator) < 0) goto out; spectator = -1; }
  struct pollfd pollfd = {.fd = o->fd, .events = POLLIN};
  int ready;
  do { ready = poll(&pollfd, 1, 5000); } while (ready < 0 && errno == EINTR);
  if (ready <= 0 || !(pollfd.revents & POLLIN)) { if (!ready) errno = ETIMEDOUT; goto out; }
  struct v4l2_buffer b = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
  if (call(o->fd, VIDIOC_DQBUF, &b) < 0) goto out;
  if (b.index >= o->count || b.flags & V4L2_BUF_FLAG_ERROR ||
   b.bytesused != o->format.fmt.pix.sizeimage || b.bytesused > o->maps[b.index].length ||
   b.timestamp.tv_sec < 0 || b.timestamp.tv_usec < 0 || b.timestamp.tv_usec >= 1000000 ||
   b.request_fd || b.reserved2 || b.flags & V4L2_BUF_FLAG_REQUEST_FD) { errno = EIO; r->errors++; goto out; }
  uint64_t stamp = (uint64_t)b.timestamp.tv_sec * 1000000 + (uint64_t)b.timestamp.tv_usec;
  if (n) {
   if (stamp <= previous || b.sequence <= sequence) { errno = EIO; goto out; }
   uint64_t delta = stamp - previous;
   if (!r->min_us || delta < r->min_us) r->min_us = delta;
   if (delta > r->max_us) r->max_us = delta;
   r->sum_us += delta;
   if (b.sequence != sequence + 1) r->gaps++;
  }
  previous = stamp; sequence = b.sequence;
  records[nrecords++] = (struct sample){phase, b.sequence, b.index, b.bytesused, stamp};
  r->frames++;
  if (call(o->fd, VIDIOC_QBUF, &b) < 0) goto out;
 }
 if (stop(o) < 0 || shape_unchanged(o) < 0) goto out;
 result = 0;
out:
 if (spectator >= 0 && close(spectator) < 0) result = -1;
 return result;
}
int main(int argc, char **argv)
{
 struct utsname uts; char *end; unsigned long input;
 if (argc != 4 || uname(&uts) || strcmp(uts.release, "7.2.0-mipad2-integrated-r3")) return 2;
 errno = 0; input = strtoul(argv[2], &end, 10);
 if (errno || *end || !*argv[2] || input > 255) return 2;
 umask(077);
 int tracefd = open(argv[3], O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
 if (tracefd < 0) return 2;
 struct owner o = {.fd = -1}; struct result results[PHASES] = {{0}};
 struct v4l2_format first = {0}; bool have_first = false;
 int result = 1, saved_errno = 0;
 if (prepare(&o, argv[1], (unsigned)input) < 0) goto out;
 first = o.format; have_first = true;
 for (unsigned phase = 0; phase < PHASES; phase++) {
  if (phase == PHASES - 1) {
   if (cleanup(&o) < 0 || prepare(&o, argv[1], (unsigned)input) < 0) goto out;
   if (!same_shape(&first, &o.format)) { errno = EIO; goto out; }
  }
  if (capture(&o, argv[1], phase, &results[phase]) < 0) goto out;
 }
 result = 0;
out:
 saved_errno = errno;
 if (cleanup(&o) < 0) result = 1;
 FILE *trace = fdopen(tracefd, "w");
 if (!trace) { close(tracefd); result = 1; }
 else {
  fprintf(trace, "phase,sequence,index,bytes,timestamp_us\n");
  for (unsigned i = 0; i < nrecords; i++) {
   struct sample *s = &records[i];
   fprintf(trace, "%u,%u,%u,%u,%" PRIu64 "\n", s->phase, s->sequence, s->index, s->bytes, s->timestamp_us);
  }
  if (fclose(trace)) result = 1;
 }
 printf("{\"exit\":%d,\"errno_on_failure\":%d,\"width\":%u,\"height\":%u,\"sizeimage\":%u,\"pixel_format\":%u,\"phases\":[",
  result, result ? saved_errno : 0, have_first ? first.fmt.pix.width : 0,
  have_first ? first.fmt.pix.height : 0, have_first ? first.fmt.pix.sizeimage : 0,
  have_first ? first.fmt.pix.pixelformat : 0);
 for (unsigned i = 0; i < PHASES; i++) {
  struct result *r = &results[i];
  printf("%s{\"frames\":%u,\"sequence_discontinuities\":%u,\"buffer_errors\":%u,\"observer_busy_checks\":%u,\"min_interval_us\":%" PRIu64 ",\"max_interval_us\":%" PRIu64 ",\"sum_interval_us\":%" PRIu64 "}",
   i ? "," : "", r->frames, r->gaps, r->errors, r->observer_busy_checks, r->min_us, r->max_us, r->sum_us);
 }
 puts("]}");
 return result;
}
