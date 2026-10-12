# Pending audit from inspected source, 2026-10-12

These are source observations/leads, not executed hardware failures or R14
fixes. Do not edit the pinned source while the R14 full build is active.

## Default capture and frame intervals

R14 VTS correction makes tiny defaults legal with respect to control ranges.
That alone does not establish safe sensor/ISP frame rates. The corrected v2
default probe now ran WITHOUT S_PARM or exposure override:4x4/8x8/16x16/22x32
and640x480 all returned zero frames then timed out, although their default
VBLANK ranges/values were valid. G_PARM periods were respectively63/156250,
147/312500,189/312500,273/312500 and21/2500 (roughly2480/2126/1653/1145/119fps).
1280x960 and1280x720 default1302/78125 (~60fps) each captured48 frames over
four restart/takeover phases. The30fps14-case and21-case matrices both pass.
Thus the high-rate default failure is real, not the former CLI-label parser
abort. Keep all negatives. Safe60fps for all other geometries is NOT proven.
The source's high_speed_mode/cache interaction still needs auditing; these
are sequential format tests, not a claim of untouched first-open startup.

Additional requested60/120fps diagnosis now ran20cases across both sensors,
16captured48frames (768frames),4front cases timed out withzero frames. The
strict1% returned-period vs delivered-rate gate FAILED on rear1920x1440:
G_PARM returned51.205fps but observed roughly31–32fps. Do not weaken/declare
that rate supported, assume PLL cause, or equate source vs delivered clocks
without live timing-register/sequence evidence. Other positive cases include
front4x4 and1298x32 at120fps: a blanket60fps sensor limit is not supported by
these observations. Front640x480 at119fps,1280x720 at80fps and1920x1440 at
40fps failed. Those failed requests hit VBLANK4 at the selected sensor height.

A separate24case front VBLANK sweep WITHOUT S_PARM now retains11zero-frame
timeouts and13*48=624positive frames. Tested4/8blank fail on all four shapes.
4x4 and640x480 start capturing atblank12;1280x720 at16;1920x1440 at32 (among
tested values4/8/12/16/32/64, not exact silicon minima). Tiny4x4 reported up to
~1860fps but delivered~640fps, and1920x1440 reported~40fps but delivered~27fps.
Thus adding blanking can remove timeouts but is NOT alone proof of truthful
frame intervals or full timing support. Some limitations may be sensor,
firmware/ISP throughput, timestamps or capture/requeue behavior; causal layer
unresolved. Test default/interval boundaries with live HTS/VTS/output/binning
registers and pre/post-REQBUFS sensor state before coding arbitrary limits.

Current atomisp_enum_frameintervals delegates to sensor enum_frame_interval
with ACTIVE state and a fixed atomisp_in_fmt_conv[0].code, forwards logical
output dimensions without accounting for padding, and can only fill a
DISCRETE answer. Both integrated sensor drivers currently have no such pad
callback. Thus the two compliance warnings are genuinely unresolved.

The sensors' S/G_INTERVAL support arbitrary rounded VTS, not only15/30fps.
OV5693: HTS2688, board pixel rate160MHz, height+VBLANK limits through65535;
T4KA3: HTS3440, pixel rate3440*2492*30, minVBLANK4+(binning-1)*height,
maxVBLANK65535-height, defaultVTS2492. A fabricated preferred15/30 discrete
list would omit the implemented timing space. A control-derived theoretical
STEPWISE range also needs physical safe-rate evidence, especially at tiny
crops. Querying cached ACTIVE VBLANK limits for a different TRY geometry is
not valid. Do not mutate ACTIVE formats/crops/controls just to enumerate.

Primary API contracts checked:
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-enum-frameintervals.html
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/vidioc-g-parm.html

## Streaming compliance / legacy buffer metadata

New real --streaming=60 compliance remains FAILED. Starting input0 timed out
at180seconds after metadata/input1 buffer tests, before a streaming test
summary. Starting input1 completed83tests/77success/6failure/2warnings:
first MMAP DQBUF failed g_request_fd(), then remaining MMAP variants cascaded
through can_stream. Both runs were reaped, camera fd ownership cleared,
sensor state restored, and subsequent RTC passed. Do not call this full
streaming compliance, or assume the input0 timeout has the same cause.

Exact loaded-version v4l-utils1.32 buffer rule checks request_fd==0 when the
REQUEST_FD flag is absent and reserved2==0. Local VB2 __fill_v4l2_buffer already
clears both. But atomisp_dqbuf_wrapper subsequently writes frame->exp_id into
buf->reserved (the request_fd union alias) and frame_config_id into reserved2.
This is a concrete legacy-ABI collision, not uninitialized VB2 memory. Audit
private 3A/per-frame Android HAL consumers before discarding their tags;
standard V4L2 must get valid reserved fields, with explicit legacy opt-in or
an appropriately versioned private metadata path if compatibility is needed.

Primary test source:
https://raw.githubusercontent.com/gjasny/v4l-utils/v4l-utils-1.32.0/utils/v4l2-compliance/v4l2-test-buffers.cpp

## Additional sensor-selection lead

OV5693 set_selection clamps left/top to the inclusive native width/height,
then bounds requested width/height by native-left/native-top. At that edge,
the resulting rectangle can become zero-sized despite the earlier minimum
clamp. Later set_fmt/calc_vts divisions assume positive dimensions. This is
an unexecuted static lead: create source-extracted invalid/edge-crop tests
before proposing a fix; do NOT try a known divide-by-zero path on the tablet.
R14 internal centered crop requests remain bounded and positive; this does
not make all user-issued subdev selections safe. Also audit ALIGN overflow,
ACTIVE streaming selection mutations and ignored control-range/set errors.

Full 3A/AWB/image quality, app GUI/recording/closing, other hardware and
flash-tools integration remain open. User hearing deferred; no tones sent.
