# Mi Pad 2 6.14 r10: measured candidate, not full completion

Date: 2026-10-11. Source: `f81a9d03d5104c47636a24952ffcd96877ccb12b`.
Release: `6.14.0-mipad2-integrated-r10`.
Boot ID: `0c95a5af-baf9-43f5-b33b-d6b25dbc2646`.

## Build and deployment

- LLVM21 ThinLTO W=1 bzImage + modules build exit 0; existing warnings remain.
- Only LOCALVERSION config difference; protected r9 build artifacts unchanged.
- 34 signed modules: CMS signatures verified against the build certificate.
- Kernel SHA256: `e72015a4bddfffc9dc2d501d739dca5a28bfda824b48ab4f4bc81b5a791fc4d2`.
- Bundle SHA256: `2e27978a368be181c0ee79dd24dd2ab6d02d390c9cc67b635570107177dabde6`.
- Candidate under /var/lib/mipad2-kernel, not replacement of stable /boot files.
- Protected one-shot GRUB boot, next_entry consumed; saved default bqdiag1.
- SSH, USB serial and no-idle inhibitor restored. Generic in-tree TFA989x,
  not the experimental OEM amplifier module.

## Real camera queues and ABI

Both front and rear passed the original strict multiopen test (18 frames
each) and a separate 320-frames-per-phase version (960 each). Nonowner
REQBUFS/QBUF/STREAMON/STREAMOFF returned EBUSY. Owner continued after observer
close. Owner mappings were unmapped before close; surviving fd allocated a
fresh queue and captured good payloads with strictly increasing sequences.
1,956 frames total; no new dmesg lines during these tests. Sensor crop,
format and controls restored with readback; no restoration errors.

Corrected stream-parameter ABI test passed on both sensors, using Atom ISP
subdev for RUN_MODE. Actual video_ioctl2 masks private CI_MODE flags; this
is covered by the 51-case host regression and the hardware assertion that
such flags do not change mode. Host tests also cover completion/flush/reset,
100,000 fallback sequence completions, u32 wrap and legacy SOF behavior.
Host tests use stubs and are not real lockdep/firmware/DMA verification.

The fallback counts ISP-returned output frames, including invalid frames;
flush and failed STREAMON completions do not advance it. It does NOT claim
sensor-side dropped-frame visibility. Firmware exposure IDs are not used
as a drop counter.

## Resume, audio and desktop

10-second RTC s2idle resumed with same boot ID; S0I3 residency +9,627,776 us.
Post-resume hardware smoke passed. Silent PCM checks verified RT5659 DAC_REF
route/hardware registers and both amplifier active/idle transitions, without
a mixer/cache repair. No kernel BUG/WARNING/UBSAN/Call Trace in that audit.
User subsequently heard both 1-second 440 Hz tones (unchanged volume 0.47).

Native Snapshot r5 binary was verified. First unfocused readiness run failed
its 48-second automation gate; it was preserved, not relabeled PASS. User
focused the window and confirmed preview. Three subsequent graceful reopens
passed native MMAP + continuing AE-frame checks. Photos were confirmed on
the earlier stable kernel, not newly re-confirmed on r10. Full automatic
white balance/3A and high-contrast AE oscillation remain separate open work.

## Open measured failures

- Cadence with S_PARM after S_FMT: front 30/15 -> 28.63/14.31 fps; rear
  30/15 -> 30.01/15.01 fps. Same-fd observer closure retained cadence.
- Surviving-fd REQBUFS resets period: front -> ~57.34 fps, rear -> ~30.01.
  The gate fails for front and rear 15 fps; no cadence fix claimed in r10.
- Video-node v4l2-compliance WITHOUT streaming: 70/74, 4 failures, 2 warnings.
  Scaling and REQBUFS/CREATE_BUFS/QUERYBUF fail once per input in each run.
  Firmware binary matching fails for 1920x1944/2460 combinations; outputs
  retained. ENUM_FRAMEINTERVALS warning remains. Not full streaming compliance.

## Source leads, not yet implemented here

Mi Pad 2 Android OV5693 modes specify a 160 MHz timing pixel clock, whereas
Linux's 167.68 MHz constant is derived from its 419.2 MHz MIPI transport.
Measured cadence ratio is consistent with these different timing/transport
clocks. Android and Linux share PLL3 timing registers but differ in the
MIPI PLL1 multiplier. Do not blindly copy MIPI register/link-frequency values.

AtomISP stop clears CSS configs. Queue setup's fallback calls S_FMT again
with a default format; sensor S_FMT resets VBLANK. Preserve selected format
and sensor timing/exposure while rebuilding CSS, then test real cadence.

Primary references:
- [Pinned Mi Pad 2 Android OV5693 modes](https://raw.githubusercontent.com/latte-dev/android_kernel_xiaomi_latte/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/ov5693.h)
- [V4L2 buffer sequence semantics](https://www.kernel.org/doc/html/v4.14/media/uapi/v4l/buffer.html)
- [V4L2 ioctl core](https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/v4l2-core/v4l2-ioctl.c)
- [CSS exposure-ID limitations](https://raw.githubusercontent.com/torvalds/linux/master/drivers/staging/media/atomisp/pci/ia_css_event_public.h)

Machine-readable companion: mipad2-6.14-r10-results.json. Raw reports,
terminal logs and package manifest retained in the development workspace.

## Exit-status correction (2026-10-11)

Earlier Snapshot r5 reopen checks proved preview readiness, not clean
process closure. They waited for pgrep disappearance without checking
systemd Result/ExecMainStatus. r10 later retained a GstGL/Mesa close-time
SIGSEGV. Do not interpret those earlier preview gates as crash-free exits.
See r11's separate Snapshot r6 four-closure status checks and limitations.
