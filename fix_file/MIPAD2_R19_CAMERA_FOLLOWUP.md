# R19 later camera application follow-up

This supplements, not rewrites, the earlier R19 hardware report. Running kernel
remains6.14.0-mipad2-integrated-r19, built source8c57f2be2; these later commits
are docs only and do not claim to be the deployed binary source.

Opt-in SnapshotR14d built source45b01add33ac,41framework tests/fullrelease
build/private installation, verified on R19 without replacing the r6 launcher:

- Four actual native JPEG shots: front2560x1920 twice, rear3264x2448 twice.
- OwnerG_INPUT read validates physical sensor0/1 before shot-onlyNULL/mode2/
  VFPP2/nativecaps;12valid full-native warmbuffers, actual sensor geometry;
  JPEGNULL decode and exact pixelsizes. No smaller rear substitute/upscale.
- Every shot restoresISPmode3/VFPP0 and fresh native1080p30 frames, not a
  cachedG_FMT-only recovery claim.
- Four post-photo10s video clips alternate rear/front/rear/front, actual
  native1920x1080H264, approximately30fps each, maximumPTSgap44.667ms (otherthree34ms); no>100ms
  gaps. Four video and four audio softwareNULL decodes pass, no playback.
- Graceful app close0, no videoowner, both sensorsPMusage0/suspended.10sRTC
  resumes unchangedboot, S0I3 increases9,715,072us, PMdebug flags restored.

Original failures remain failed: R14PREVIEW limit, R14b fixed30fps display
versus15fps native still not-linked, R14c rearT4 incorrectly treated asfront
because genericlibcamera.locationUnknown. No hidden retry or default change.
Source changes fix paired ISPmode/VFPPlease, both displayrate ceilings, and
actual physicalinput selection ratherthan Unknown-location inference.

Candidate NOT promoted; same-scene Android/Windows quality/visibleGUI/player/
rotation/AF/AWB/NR not established. Front lowgain1/2 AEchatter observed in
actual journal remains (494 filteredupdates,493 alternatingpairs); nextwork
requires fine exposure feedback, not declaring full parity from30fps alone.
Still shutterlatency approximately2seconds sampling and fullrear15fps physical
throughput also unproven. Kernelnormal-stop reset/async-recovery failure and
real busfault tests, headlessboot/highrates/compat32/Requests/DSP/otherhardware,
fullflash image build/integration remain. Fullobjective active.

Source-pinned app evidence:
- [Nativephoto/record/PM details](https://github.com/E7G/snapshot/blob/2c5c1709c3c76e57db7a5494d101191f135db7dc/MIPAD2_PHOTO_R14.md)
- [Sanitized machine-readable results](https://github.com/E7G/snapshot/blob/2c5c1709c3c76e57db7a5494d101191f135db7dc/MIPAD2_PHOTO_AUTOMATED_EVIDENCE.json)

Private images/video remain on the device; no media/credentials published.
