/* SPDX-License-Identifier: GPL-2.0 */
#define main lifecycle_device_main
#include "mipad2-7.2-r4-lifecycle-device-test.c"
#undef main

int main(void)
{
 static const struct {
  uint32_t fourcc, width, height, stride, sizeimage, payload;
 } cases[] = {
  {V4L2_PIX_FMT_YUV420, 1280, 720, 1280, 1384448, 1382400},
  {V4L2_PIX_FMT_YUV420, 1280, 720, 1280, 1382399, 0},
  {V4L2_PIX_FMT_NV12, 1920, 1080, 1920, 3112960, 3110400},
  {V4L2_PIX_FMT_NV12, 1920, 1080, 2048, 3321856, 3317760},
  {V4L2_PIX_FMT_NV12, 1920, 1080, 2047, 3321856, 0},
  {V4L2_PIX_FMT_NV12, 1920, 1080, 1918, 3321856, 0},
  {V4L2_PIX_FMT_NV12, 1920, 1079, 1920, 3112960, 0},
  {V4L2_PIX_FMT_NV12, 1920, 0, 1920, 3112960, 0},
  {V4L2_PIX_FMT_RGB24, 1920, 1080, 1920, 3112960, 0},
  {V4L2_PIX_FMT_NV12, 1920, UINT32_MAX - 1, UINT32_MAX - 1, UINT32_MAX, 0},
 };
 for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
  const struct v4l2_pix_format pix = {
   .pixelformat = cases[i].fourcc, .width = cases[i].width,
   .height = cases[i].height, .bytesperline = cases[i].stride,
   .sizeimage = cases[i].sizeimage,
  };
  uint32_t actual = linear_420_payload(&pix);
  if (actual != cases[i].payload) {
   fprintf(stderr, "layout case %zu: got %u, expected %u\n",
    i, actual, cases[i].payload);
   return 1;
  }
 }
 puts("10 capture payload layout cases passed");
 return 0;
}
