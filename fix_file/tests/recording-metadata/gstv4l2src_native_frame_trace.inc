/* SPDX-License-Identifier: LGPL-2.0-or-later */
/* Opt-in, bounded metadata in caller-precreated tmpfs. No buffer/flow writes. */
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define MP2_FRAME_CAPACITY 4096
typedef struct {
  char magic[8];
  guint32 version, record_size;
  guint64 capacity, pid, count, dropped, source_count, error_flags;
} Mp2FrameHeader;
typedef struct {
  guint64 driver_ns, pts_ns, duration_ns, driver_offset, output_offset;
  guint64 bytes, monotonic_ns, source_id, epoch, flags, bad_timestamp;
} Mp2FrameRecord;
typedef struct {
  guint64 source_id, epoch, previous_offset, previous_stamp;
  gboolean seen;
} Mp2FrameSource;
G_STATIC_ASSERT (sizeof (Mp2FrameHeader) == 64);
G_STATIC_ASSERT (sizeof (Mp2FrameRecord) == 88);
static gsize mp2_frame_initialized;
static GQuark mp2_frame_key;
static Mp2FrameHeader *mp2_frame_header;
G_LOCK_DEFINE_STATIC (mp2_frame_lock);

static void
mp2_native_frame_trace (GstObject *source, GstBuffer *buffer,
    guint64 driver_ns, guint64 driver_offset, gboolean bad_timestamp)
{
  Mp2FrameSource *state;
  Mp2FrameRecord record;
  struct timespec now;
  if (g_once_init_enter (&mp2_frame_initialized)) {
    const char *path = g_getenv ("MIPAD2_V4L2_NATIVE_FRAME_TRACE");
    gsize enabled = 1;
    if (path && path[0] == '/') {
      struct stat st;
      const size_t bytes = sizeof (Mp2FrameHeader) +
          MP2_FRAME_CAPACITY * sizeof (Mp2FrameRecord);
      int fd = open (path, O_RDWR | O_NOFOLLOW | O_CLOEXEC);
      if (fd >= 0) {
        if (fstat (fd, &st) == 0 && S_ISREG (st.st_mode) &&
            st.st_uid == getuid () && st.st_nlink == 1 &&
            (st.st_mode & 0777) == 0600 && st.st_size == (off_t) bytes) {
          void *mapping = mmap (NULL, bytes, PROT_READ | PROT_WRITE,
              MAP_SHARED, fd, 0);
          if (mapping != MAP_FAILED) {
            Mp2FrameHeader zero = { 0 };
            if (memcmp (mapping, &zero, sizeof zero) == 0) {
              mp2_frame_header = mapping;
              memcpy (mp2_frame_header->magic, "MP2V4F01", 8);
              mp2_frame_header->version = 1;
              mp2_frame_header->record_size = sizeof (Mp2FrameRecord);
              mp2_frame_header->capacity = MP2_FRAME_CAPACITY;
              mp2_frame_header->pid = getpid ();
              mp2_frame_key = g_quark_from_static_string (
                  "mipad2-v4l2-native-frame-trace-v1");
              enabled = 2;
            } else {
              munmap (mapping, bytes);
            }
          }
        }
        close (fd);
      }
      if (enabled != 2)
        g_printerr ("MP2_V4L2_NATIVE_TRACE rejected metadata file\n");
    }
    g_once_init_leave (&mp2_frame_initialized, enabled);
  }
  if (mp2_frame_initialized != 2)
    return;

  G_LOCK (mp2_frame_lock);
  state = g_object_get_qdata (G_OBJECT (source), mp2_frame_key);
  if (!state) {
    state = g_new0 (Mp2FrameSource, 1);
    state->source_id = ++mp2_frame_header->source_count;
    g_object_set_qdata_full (G_OBJECT (source), mp2_frame_key, state, g_free);
  }
  /* Observed reset boundary, not a synthesized sequence or sensor counter. */
  if (state->seen &&
      ((driver_offset != GST_BUFFER_OFFSET_NONE &&
          state->previous_offset != GST_BUFFER_OFFSET_NONE &&
          driver_offset <= state->previous_offset) ||
       (driver_ns != GST_CLOCK_TIME_NONE &&
          state->previous_stamp != GST_CLOCK_TIME_NONE &&
          driver_ns < state->previous_stamp)))
    state->epoch++;
  state->seen = TRUE;
  state->previous_offset = driver_offset;
  state->previous_stamp = driver_ns;
  if (mp2_frame_header->count >= MP2_FRAME_CAPACITY) {
    mp2_frame_header->dropped++;
    G_UNLOCK (mp2_frame_lock);
    return;
  }
  if (clock_gettime (CLOCK_MONOTONIC, &now) != 0) {
    mp2_frame_header->error_flags |= 1;
    G_UNLOCK (mp2_frame_lock);
    return;
  }
  record = (Mp2FrameRecord) {
    driver_ns, GST_BUFFER_PTS (buffer), GST_BUFFER_DURATION (buffer),
    driver_offset, GST_BUFFER_OFFSET (buffer), gst_buffer_get_size (buffer),
    (guint64) now.tv_sec * GST_SECOND + now.tv_nsec,
    state->source_id, state->epoch, GST_BUFFER_FLAGS (buffer), bad_timestamp
  };
  memcpy ((char *) mp2_frame_header + sizeof (Mp2FrameHeader) +
      mp2_frame_header->count * sizeof record, &record, sizeof record);
  mp2_frame_header->count++;
  G_UNLOCK (mp2_frame_lock);
}
