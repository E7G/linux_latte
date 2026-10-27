/* SPDX-License-Identifier: MIT
 * Private generated-input probe. No preload, frame mutation, drop or retiming.
 * Attach only to an owned GstPipeline; finish only after it reaches NULL. */
#include <gst/gst.h>
#include <gst/video/video.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

struct mp2_layout {
    uint32_t width, height, planes, nv12;
    uint64_t offset[2];
    int32_t stride[2];
};
static void hex_digest(const unsigned char *data, char result[65])
{
    static const char hex[] = "0123456789abcdef";
    for (unsigned i = 0; i < 32; i++) {
        result[2*i] = hex[data[i] >> 4];
        result[2*i+1] = hex[data[i] & 15];
    }
    result[64] = 0;
}
int mp2_nv12_hash(const unsigned char *data, uint64_t size,
                 const struct mp2_layout *layout, char visible[65], char storage[65])
{
    if (!data || !layout || !visible || !storage || size < 3110400 ||
        size >= 16*1024*1024 || layout->width != 1920 || layout->height != 1080 ||
        layout->planes != 2 || layout->nv12 != 1)
        return 0;
    const unsigned heights[2] = {1080, 540};
    uint64_t ends[2];
    for (unsigned p = 0; p < 2; p++) {
        if (layout->offset[p] >= size || layout->stride[p] < 1920 ||
            (uint64_t)layout->stride[p] > size || (layout->stride[p] & 1))
            return 0;
        ends[p] = layout->offset[p] + (heights[p]-1)*(uint64_t)layout->stride[p]+1920;
        if (ends[p] > size)
            return 0;
    }
    if ((layout->offset[1] & 1) || ends[0] > layout->offset[1])
        return 0;
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx)
        return 0;
    int okay = EVP_DigestInit_ex(ctx, EVP_sha256(), NULL);
    for (unsigned p = 0; okay && p < 2; p++) {
        for (unsigned row = 0; okay && row < heights[p]; row++) {
            const uint64_t begin = layout->offset[p]+row*(uint64_t)layout->stride[p];
            okay = EVP_DigestUpdate(ctx, data+begin, 1920);
        }
    }
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned bytes = 0;
    okay = okay && EVP_DigestFinal_ex(ctx, digest, &bytes) && bytes == 32;
    if (okay)
        hex_digest(digest, visible);
    okay = okay && EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) &&
           EVP_DigestUpdate(ctx, data, (size_t)size) &&
           EVP_DigestFinal_ex(ctx, digest, &bytes) && bytes == 32;
    if (okay)
        hex_digest(digest, storage);
    EVP_MD_CTX_free(ctx);
    return okay;
}
struct row {
    struct mp2_layout layout;
    uint64_t pts, duration, storage_bytes;
    char visible[65], storage[65];
};
struct probe {
    GstElement *pipeline;
    GstPad *pad;
    gulong id;
    gint count, error;
    uint64_t hash_wall_ns, hash_cpu_ns, copy_wall_ns, copy_cpu_ns;
    unsigned char *scratch;
    size_t capacity;
    struct row rows[180];
};
static uint64_t ns(clockid_t kind)
{
    struct timespec t;
    if (clock_gettime(kind, &t))
        return 0;
    return (uint64_t)t.tv_sec*1000000000ULL+(uint64_t)t.tv_nsec;
}
static GstPadProbeReturn observe(GstPad *pad, GstPadProbeInfo *info, gpointer data)
{
    struct probe *p = data;
    GstBuffer *buffer = GST_PAD_PROBE_INFO_BUFFER(info);
    GstCaps *caps = gst_pad_get_current_caps(pad);
    GstVideoInfo video;
    GstVideoMeta *meta = buffer ? gst_buffer_get_video_meta(buffer) : NULL;
    const gint index = g_atomic_int_get(&p->count);
    gboolean valid = caps && gst_video_info_from_caps(&video, caps) &&
        GST_VIDEO_INFO_WIDTH(&video) == 1920 && GST_VIDEO_INFO_HEIGHT(&video) == 1080 &&
        GST_VIDEO_INFO_FORMAT(&video) == GST_VIDEO_FORMAT_NV12 && meta &&
        buffer && gst_buffer_n_memory(buffer) == 1 && index < 180;
    if (caps)
        gst_caps_unref(caps);
    if (!valid) {
        g_atomic_int_set(&p->error, 1);
        return GST_PAD_PROBE_OK;
    }
    struct row *r = &p->rows[index];
    r->layout = (struct mp2_layout){meta->width, meta->height, meta->n_planes,
                                  meta->format == GST_VIDEO_FORMAT_NV12,
                                  {meta->offset[0], meta->offset[1]},
                                  {meta->stride[0], meta->stride[1]}};
    r->pts = GST_BUFFER_PTS(buffer);
    r->duration = GST_BUFFER_DURATION(buffer);
    GstMapInfo map = GST_MAP_INFO_INIT;
    if (!gst_buffer_map(buffer, &map, GST_MAP_READ)) {
        g_atomic_int_set(&p->error, 2);
        return GST_PAD_PROBE_OK;
    }
    const uint64_t wall = ns(CLOCK_MONOTONIC), cpu = ns(CLOCK_THREAD_CPUTIME_ID);
    r->storage_bytes = map.size;
    valid = map.size == gst_buffer_get_size(buffer) && map.size >= 3110400 && map.size < 16*1024*1024;
    if (valid && p->capacity < map.size) {
        unsigned char *next = g_try_realloc(p->scratch, map.size);
        if (!next)
            valid = FALSE;
        else {
            p->scratch = next;
            p->capacity = map.size;
        }
    }
    /* Ordinary synchronized map and one complete read-only memcpy. Hash the
     * private CPU snapshot, never bypass GPU/cache synchronization or mutate
     * mapped storage. This avoids repeated CPU reads from a WC allocation. */
    if (valid)
        memcpy(p->scratch, map.data, map.size);
    p->copy_wall_ns += ns(CLOCK_MONOTONIC)-wall;
    p->copy_cpu_ns += ns(CLOCK_THREAD_CPUTIME_ID)-cpu;
    const uint64_t hash_wall = ns(CLOCK_MONOTONIC), hash_cpu = ns(CLOCK_THREAD_CPUTIME_ID);
    valid = valid && mp2_nv12_hash(p->scratch, map.size, &r->layout, r->visible, r->storage);
    p->hash_wall_ns += ns(CLOCK_MONOTONIC)-hash_wall;
    p->hash_cpu_ns += ns(CLOCK_THREAD_CPUTIME_ID)-hash_cpu;
    gst_buffer_unmap(buffer, &map);
    if (valid)
        g_atomic_int_set(&p->count, index+1);
    else
        g_atomic_int_set(&p->error, 3);
    return GST_PAD_PROBE_OK;
}
void *mp2_probe_attach(GstElement *pipeline)
{
    if (!pipeline || !GST_IS_PIPELINE(pipeline) || GST_STATE(pipeline) != GST_STATE_NULL)
        return NULL;
    GstElement *encoder = gst_bin_get_by_name(GST_BIN(pipeline), "encoder");
    if (!encoder)
        return NULL;
    GstPad *pad = gst_element_get_static_pad(encoder, "sink");
    gst_object_unref(encoder);
    if (!pad)
        return NULL;
    struct probe *p = g_new0(struct probe, 1);
    p->pipeline = gst_object_ref(pipeline);
    p->pad = pad;
    p->id = gst_pad_add_probe(pad, GST_PAD_PROBE_TYPE_BUFFER, observe, p, NULL);
    if (!p->id) {
        gst_object_unref(p->pipeline);
        gst_object_unref(pad);
        g_free(p);
        return NULL;
    }
    return p;
}
int mp2_probe_error(void *handle)
{
    return handle ? g_atomic_int_get(&((struct probe *)handle)->error) : -1;
}
char *mp2_probe_finish(void *handle)
{
    struct probe *p = handle;
    if (!p || GST_STATE(p->pipeline) != GST_STATE_NULL)
        return NULL;
    gst_pad_remove_probe(p->pad, p->id);
    const unsigned count = (unsigned)g_atomic_int_get(&p->count);
    GString *s = g_string_new(NULL);
    g_string_append_printf(s, "{\"error\":%d,\"count\":%u,\"hash_wall_ns\":%" G_GUINT64_FORMAT
        ",\"hash_cpu_ns\":%" G_GUINT64_FORMAT ",\"copy_wall_ns\":%" G_GUINT64_FORMAT
        ",\"copy_cpu_ns\":%" G_GUINT64_FORMAT ",\"rows\":[",
        g_atomic_int_get(&p->error), count, p->hash_wall_ns, p->hash_cpu_ns, p->copy_wall_ns, p->copy_cpu_ns);
    for (unsigned i = 0; i < count; i++) {
        const struct row *r = &p->rows[i];
        g_string_append_printf(s,
            "%s{\"index\":%u,\"PTS_ns\":%" G_GUINT64_FORMAT ",\"duration_ns\":%" G_GUINT64_FORMAT
            ",\"visible_bytes\":3110400,\"storage_bytes\":%" G_GUINT64_FORMAT
            ",\"visible_SHA256\":\"%s\",\"storage_SHA256\":\"%s\",\"layout\":{\"format\":\"NV12\","
            "\"width\":%u,\"height\":%u,\"n_planes\":%u,\"offsets\":[%" G_GUINT64_FORMAT ",%" G_GUINT64_FORMAT
            "],\"strides\":[%d,%d]}}", i ? "," : "", i, r->pts, r->duration, r->storage_bytes,
            r->visible, r->storage, r->layout.width, r->layout.height, r->layout.planes,
            r->layout.offset[0], r->layout.offset[1], r->layout.stride[0], r->layout.stride[1]);
    }
    g_string_append(s, "]}");
    gst_object_unref(p->pad);
    gst_object_unref(p->pipeline);
    g_free(p->scratch);
    g_free(p);
    return g_string_free(s, FALSE);
}
void mp2_probe_free_string(char *s)
{
    g_free(s);
}
