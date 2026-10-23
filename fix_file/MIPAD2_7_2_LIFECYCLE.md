# 7.2 r3: native buffer lifecycle evidence, not complete recording qualification

The requested upstream is still E7G/linux_latte@9928c7b8d00c500ee97903afa1cc76c1c36ab2bc.
Actual kernel C/build source is `20f0304fc024a784dd2e356bd72331c9640d382e`.
This checkpoint adds a measured userspace device fixture and its syscall oracle,
not a new driver patch, kernel build, stable default or complete image.

## Actual device scope

On `7.2.0-mipad2-integrated-r3`, each OV5693 front/T4KA3 rear input completed:

- Default 1280x720 YU12: 480 raw buffers per camera, four 120-frame phases.
- Explicit 1920x1080 NV12: another 480 per camera, four 120-frame phases.
- The first three phases reuse the owning file/MMAP allocation after STREAMOFF;
  the fourth closes/releases that owner and opens/reallocates a new owner.
- Each phase opens a nonowner during capture; four nonowner allocation/queue/
  start/stop requests return EBUSY. Closing that spectator must leave production
  running. In total 64 negative ownership checks across the four camera/profile
  combinations passed, with 1920 dequeued buffers and no sequence discontinuity
  or V4L2 buffer-error flag.
- Largest timestamp interval: 34.165 ms at default format, 33.906 ms at NV12.
  Software-completion timestamps are not sensor SOF or physical conservation.

No S_FMT/S_PARM or sensor-control write occurs inside the measured C helper.
The NV12 controller explicitly negotiates that format before each helper, rather
than misrepresenting a 720p run as full-quality video. No pixel is copied/saved;
per-frame metadata is buffered in RAM and written privately only after streaming
ends. The test does not decode frames, assess live preview/optics, encode MP4/AAC
or prove that application recording no longer stutters. No failed-reset fault
was injected; normal cleanup is not proof of a physical DMA fence on failure.

## Important failed-controller result and correction

The first NV12 controller ended **failed**, despite both captures passing,
because it restored T4KA3 output format before the crop rectangle. The crop
setter deliberately resets output size when crop dimensions change; applying it
last removed the saved 2x binning (1296x736 became 2592x1472). This was a test
restoration-order error, not evidence of a broken sensor crop implementation.

The failed receipt is retained. A separate read-only audit identified the exact
remaining difference; reapplying the saved output format after the already
restored crop corrected it. Both sensors' saved geometry/captured controls, the
video format and selected input were then independently read back equal, without
recapturing or changing the kernel. Future controllers restore crop FIRST,
then output format/binning, then captured controls. The original control subset
was not every possible sensor control; do not claim complete device-state capture.

All kernel fault deltas were zero; both sensors and ISP ended runtime-suspended
with usage zero. Raw CSV, MMAP/pointer/kernel/serial evidence remains private.
The previous approximately 3.5-hour device freeze remains unexplained; these
short passes do not certify long-term stability or justify default promotion.

## Reproducible synthetic oracle, no hardware access

```sh
python3 fix_file/tests/mipad2-7.2-r3-lifecycle-host-test.py
python3 -O fix_file/tests/mipad2-7.2-r3-lifecycle-host-test.py
```

The host shim includes the actual measured C source and replaces its syscalls.
ASan/UBSan check the positive path plus malformed ownership, spectator-close
regression, timeout, duplicate/backwards timestamp, payload/error/metadata,
STREAMOFF and shape mutations. The C helper reports sequence gaps as counters:
**exit zero alone is insufficient**. The test's strict gate rejects the gap
mutation even when the helper exits zero. This is a test-oracle regression,
not a mocked proof of actual driver failure handling.

For an actual device run, do not call the binary blindly: ensure the exact r3
release/AtomISP input, an otherwise idle camera, thermal/space guards and a NEW
private trace path; snapshot/restore input, video format, both sensors' crop,
format and relevant controls. Never switch/reprobe after a hardware fence failure
or restart a still-live probe merely because observation expired. This fixture
is pinned to r3 and cannot run on an arbitrary kernel just by accident.

## 7.2 userspace handoff is still a separate gate

Actual r3 has `Left Amp Input` / `Right Amp Input`, not old `Amp Input` /
`Amp Input1`. The tablet's old manually installed UCM profile referenced those
two absent controls. Published dual-family UCM pkgrel8 was staged, parsed using
the real hardware ALSA parser and installed with a private old-file backup.
System `_verbs` and `_devices/HiFi` queries pass with byte-identical mixer state;
no verb/device activation, audio-service restart, playback or acoustic test was
performed. Do not call that a successful physical speaker/microphone test.

The existing `linux-latte-integrated-7-2` r3 native artifact is explicitly a
**kernel-only verified binary repack** (104 archive members), with no UCM payload.
It is not the source-CI complete support-payload path and cannot alone be called
a complete system image. Source-CI builds stage shared platform files; common
file ownership when co-installing 6.14/7.2 packages still needs a dedicated audit.
Avoid inventing a separately installed package without checking those conflicts.

Scalar evidence: [device summary](tests/mipad2-7.2-r3-lifecycle-device-summary.json).
Outstanding gates include normal-app long front/rear MP4/AAC/live pacing,
AE/AWB/focus and optical quality, actual 7.2 audio, suspend/resume/S0I3/S5,
failed-reset DMA quiescence, long-freeze attribution and full image qualification.
The complete kernel/system and Android/Windows parity objective remains active.
