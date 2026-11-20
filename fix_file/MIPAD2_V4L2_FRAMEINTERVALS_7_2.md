# Mi Pad 2 7.2: crop-dependent frame intervals

LPAT11 implements capture `G_PARM`/`S_PARM` on both cameras but returns
`ENOTTY` from `VIDIOC_ENUM_FRAMEINTERVALS`. A single 30 fps value is
not a substitute for the sensor controls: the maximum changes
with crop, horizontal/vertical binning and sensor-specific margins.

The LPAT12 candidate uses the standard
[STEPWISE interval ABI](https://docs.kernel.org/userspace-api/media/v4l/vidioc-enum-frameintervals.html).
AtomISP negotiates the requested FourCC and geometry in TRY state,
passes the locked padded format and crop to the sensor, and gets an
exact range with one frame-length line per step. It returns `EINVAL`
for a non-zero index or if the requested format would have to be
adjusted. The ioctl does not select a sensor, set ACTIVE state, power
the hardware or program a frame interval. Existing discrete sensors
keep their previous callback. The range describes accepted timing
requests, not a measured promise about ISP or encoder throughput.

## GStreamer 1.28.7 compatibility

The unpatched probe expands each step into a GStreamer fraction list.
On the installed runtime, the 1920×1440 timing model overflows the
fraction arithmetic at the first or third entry; omitting the normal
30 fps requests from both lists is a compatibility regression.
Do not treat kernel-only testing as a desktop qualification.

`gstreamer-v4l2-atomisp-stepwise.patch` applies from the root of the
GStreamer 1.28.7 `gst-plugins-good` tarball, after the existing
`gstreamer-v4l2src-early-latency.patch`. It affects only AtomISP
stepwise probing. It reports a bounded range of accepted requests
to GStreamer instead of materializing thousands of line timings;
`S_PARM` still quantizes requests and reports the actual period.
Other V4L2 drivers and discrete/continuous enumeration stay unchanged.
This does not make GStreamer’s global caps describe a different frame
rate range for every size in its integer size range.

## Qualification

* Kernel host tests exercise 14,760 TRY crop/range combinations, format
  and index rejection, exact known 1080p timing, and independent sensor
  locking/geometry, current interval and exposure regressions.
* The GStreamer helper extracted from the patched source was checked
  with the tablet’s GStreamer runtime. For 1080p and 1920×1440 it
  accepts nominal 30 fps and the exact 30.002 fps front rate, rejects an
  out-of-range 120 fps, and handles malformed/equal interval endpoints.
* The replacement plugin, loaded from a private path with a private
  registry on LPAT11, passed six positive captures across the two
  resolutions, inputs and nominal/native rate requests. No system
  package or plugin was replaced; LPAT11 has no stepwise callback.
* Remaining gate: build/sign LPAT12, verify native enumeration and
  `S_PARM` round trips for both sensors including during a competing
  read-only enumeration client, and run old/new GStreamer controls
  on the same candidate. Keep the known-good boot and user-space
  backend until the pair has been tested.
