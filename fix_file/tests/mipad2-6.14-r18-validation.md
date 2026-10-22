# R18 scoped hardware evidence — full integration remains incomplete

2026-10-12. Built source `86c16f5c75fefb42c5b6c89025d2f5475c912f45`;
actual one-shot kernel `6.14.0-mipad2-integrated-r18`, boot
`7f31a0fb-7ff1-4793-8694-9c0e76db6797`. Saved stable default remains
`mipad2-bqdiag1`. R17 protected artifacts and unrelated dirty files preserved.

## Production fixes and bounded causal evidence

Only T4 fixed-line-length read-only HBLANK callback registration (NULL ops)
and both sensors' HAS_EVENTS flags changed. Existing 6.14 core handles events;
no fabricated events, duplicate callbacks or swallowed exposure/I2C failures.
Sixteen source-extracted host suites and actual kernel-header compilation pass;
stubs do not prove real I2C rollback. Full pinned LLVM21 ThinLTO bzImage/modules
build passed, all34 module CMS signatures verified, protected append-only stage
and early serial initrd verified, real R18 boot/SSH recovered.

A controlled REAL R17 baseline held T4 runtime-active: effective width1934
S_FMT returnedEINVAL; ACTIVE width mutated while HBLANK value1504 disagreed
with range/default1506. Suspended restoration succeeded. R18 held-active
1934/repeated1934/1936 all succeed, HBLANK range/default/value agree at
1506/1506/1504. Original PM policy, both sensor shapes/full writable scalar
values and video1280x720 restored. This is NOT complete crop/control/PM/I2C
error-path transactional proof.

## Hardware gates and retained own test defects

Both sensors' unmodified generic ioctl compliance now46/46, warnings0; no
pad-geometry section appears in that tool output. Independent guarded pad
fixture:6cases x240frames =1440frames,24 ACTIVE streaming EBUSY phases,
effective per-FD TRY isolation, metadata/restart/takeover and30fps1% checks.
Both-start video streaming compliance83/83, warnings2 each. Ten idle crop
extremes, strict queues, ordinary restart, CREATE_BUFS size/stream contracts,
warm modes, scaling/even-size matrices, longmetadata and39 default/min cases
(9360frames) pass. Default cases establish30fps1%; minimum cases are not a
physical maximum-FPS claim. All sampled restorations include pattern/flips.

The first powered probe passed its actual width/HBLANK cases but FAILED its
video restoration: our loop overwrote the global width used by restore. Its
original report remains failed. Saved-state recovery restored the exact first
snapshot; v2 fixes the loop and captures restore arguments and passes.

The first per-FD event fixture FAILED after receiving its first valid event:
it wrongly expectedEAGAIN for an empty queue. Actual6.14 core returnsENOENT.
No kernel change made to mask this. Six compiled positive/negative helper
cases pass; corrected actual per-FD fixture passes BOTH sensors: initial and
change events, poll, increasing sequence/monotonic timestamps, no event for
same-value write, unsubscribe isolation and exposure/full sampled restoration.
Original faulty fixture/report are retained alongside corrected results.

GUI initial prelaunch guard also rejected v4l2-ctl's harmless `(Disabled)`
label; no application had launched then. After correcting only the parser,
one window was initially blocked by lockscreen. User unlocked and confirmed
front/rear normal after switching each side twice. Actual journal has real
front/rear AE samples; rear1920x1440@30 and HBLANK1504, both patterns0.
Three fresh reopen processes deliver at least6 AE samples each; initial and
two reopened processes close cleanly (status0, camera idle). Final window
remains open. We do NOT infer native backend from an absent native-MMAP log,
nor claim photos/recording/full imagery quality from AE samples.

Silent cold/post-RTC RT5659/DAC_REF/dualTFA electrical checks pass; no tones
or acoustic confirmation. Final post-hardware-camera10s RTC wake passes and
adds9,409,088us S0I3. This sample is actual low-power entry, NOT an explanation
or erasure of R17's retained0us sample. No production default replaced.

See [machine-readable summary](mipad2-6.14-r18-validation-summary.json),
retained failed reports, separate recovery/v2 reports and strict fixture.
Historical bundle manifest says not-booted because it records packaging time;
this later boot/hardware evidence supersedes it, not rewrites it.

## Still within the original objective

Full geometry/control/real-I2C/PM error transactions; physical highrates and
early cadence cause/all intervals; full3A/AWB/image quality/photos/recording;
compat32/Media Requests; broader hardware; full flash-image build and boot.
No full completion claim. R18 GUI support is an observed bounded improvement.

Primary references:
- https://github.com/torvalds/linux/blob/v6.14/drivers/media/v4l2-core/v4l2-event.c
- https://github.com/torvalds/linux/blob/v6.14/drivers/media/v4l2-core/v4l2-subdev.c
- https://docs.kernel.org/userspace-api/media/v4l/vidioc-dqevent.html
- https://docs.kernel.org/userspace-api/media/v4l/vidioc-subscribe-event.html
