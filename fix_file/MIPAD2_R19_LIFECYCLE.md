# Mi Pad 2 R19 camera lifecycle source candidate

This is source/host-test evidence, NOT a deployed kernel, hardware fault
injection result, or Android parity claim. Runtime remains R18 until an
independent full image is built and a protected one-shot boot is verified.

## Correct V4L2 caller contract

Linux 6.14 `call_s_stream()` masks negative stop errors and completes legacy
stop bookkeeping. T4KA3 also uses pad stream state via the stream helper.
Retaining a sensor PM reference after stop failure cannot be retried by simply
calling legacy stop again: the wrapper now considers it stopped. The earlier
unpublished retained-reference prototype was rejected by actual-core fixtures.

Both sensors now clear logical streaming and release exactly their own PM
reference. A failed stop requests synchronous runtime suspend; another PM user
may keep hardware powered (`-EBUSY`), so immediate power-off is NOT promised.
OV5693 caches controls and rejects uncached OTP while awaiting reinitialization,
then performs full initialization before restart if power stayed on. Successful
runtime resume clears this flag. Synchronous PM release is outside its mutex.
T4KA3 explicitly enters standby before each existing full stream initialization.
Both legacy and pad bookkeeping complete consistently on stop failure.

## AtomISP failed STREAMON unwind

The sensor starts after CSS, queued buffers, SOF IRQ, CSI and the media pipeline.
VB2 does not call `stop_streaming` after a failed `start_streaming`. The failed
sensor-start branch now stops CSS, clears counters/IRQ/CSI, returns buffers as
`VB2_BUF_STATE_QUEUED`, cleans pending parameters/events, lowers DFS, resets and
recreates streams, and releases media ownership exactly once. It preserves the
original sensor errno. Failed reset or recreation marks the ISP fatal instead
of advertising a usable pipeline.

## Evidence and limits

All 18 existing/new source-extracted host suites pass (ASan/UBSan where fixtures
enable them). The stop fixture extracts both callbacks, actual `call_s_stream`
and actual `v4l2_subdev_disable_streams`, covering 160 combinations of success/
four bus errors, foreign PM references, repeated core stop and restart.
The start fixture extracts the entire callback, covering 28 start/unwind/retry/
fatal-cleanup/pre-start cases. PM, hardware, media and CSS primitives are stubs;
this is not a proof of physical I2C/reset behavior or the entire kernel.
The warm-preview fixture only gained dependencies required to compile the new
callback; its existing assertions/case counts remain unchanged. The first
regression run's fixture compilation failure is retained separately.

Still pending: full build/boot and real stream/reopen/PM regressions; normal-stop
reset error handling; asynchronous recovery-worker failure handling; boot
reliability; full-resolution photo/video switching; AE/AWB/AF/NR and same-scene
Android image comparison; other hardware and flash-image regressions.

References:
- https://github.com/torvalds/linux/blob/v6.14/drivers/media/v4l2-core/v4l2-subdev.c
- https://docs.kernel.org/driver-api/media/v4l2-videobuf2.html
- https://docs.kernel.org/power/runtime_pm.html
