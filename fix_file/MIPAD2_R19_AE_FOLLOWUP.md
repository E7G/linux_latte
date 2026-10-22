# R19 application AE follow-up and open recovery error work

Running kernel6.14.0-mipad2-integrated-r19 remains built source8c57f2be2.
This commit is documentation/evidence only, no R20 binary built/deployed.

## R15c actual coarse-gain correction

Snapshot built78d677c9c260,44frameworktests and fullrelease/privatepackage.
Android rawgain units checked against exact sourcebytes; existing Linuxwhole
gain ABI preserved. WindowsCPF isAIQB binary tuning, not available3A source.
Old R14d actualfront494 filtered1/2 gainupdates/493 alternatingpairs were
reproduced by an exact source-extracted RED fixture. Removing gain-only
nudge firstFAILED old full44test convergence case at bright/shortexposure;
relative-step fallback alsoFAILED. Both failures retained, never deployed.
Corrected R15c quantizes downward gain ANDexposure without forced extra code
steps on delayed rounded-back corrections. Full old convergence tests remain.

Two actualfront starts at exposure1976, gains1/2 nowsettle: last20 processed
luma samples126.9..127.0 and126.9, fixed exposure/gain1825/2 and1819/2,
no gain2->1 reversal or latecontrolupdates; actualnative1080p30. This proves
the measured current-scene chatter correction, not same-scene Androidoptics
or all-scene automatic3A. Fine fractional gain and general3A support forother
applications remain independent work, not secretly changed controlunits.

Four actualnative JPEGs (front2560x1920 twice/rear3264x2448 twice) decode,
everyshot restoresISP3/VFPP0 and fresh1080p30; four postphoto10s clips alternate
rear/front/rear/front at approximately30fps, maxPTSgap34ms, no>100ms gaps.
Four video/audioNULL decodes pass, no playback or private media transfer.
After modes/recordings,20fresh front AEsamples remain steady in deadband.
Gracefulclose0/bothsensorPM0 suspended; originalsensor exposure/gain restored
exactly whileidle.10sRTC resumes sameboot, SoCS0I3+9,069,088us, PMdebug restored.
r6launcher/normalsettings/priorbinaries/stablebqdiag1 default preserved;
privatecandidateNOTpromoted. Full goal remainsactive.

[Source-pinned R15c details](https://github.com/E7G/snapshot/blob/412db163ee002c6f3838fd3cb7b5e5c5ed04d62c/MIPAD2_AE_R15.md)
[Sanitized machine-readable evidence](https://github.com/E7G/snapshot/blob/412db163ee002c6f3838fd3cb7b5e5c5ed04d62c/MIPAD2_AE_R15_AUTOMATED_EVIDENCE.json)

## R20 error recovery remains RED, not fixed

Exact R19 atomisp_assert_recovery_work source callback compiled with explicit
C hardware/CSS/VB2stubs. Normal pathpasses. Four error-return cases areRED:
reset/create failure still callsCSS/sensorstart; CSSstart failure stillstarts
sensor/enablesSOF; sensorstart failure leavesASDstreamingtrue. No fatalstate
or VB2queue-error notification is provided. Function sourceSHA matches deployed
R19 built8c57f2be2, not only current documentationHEAD. See tests/
mipad2-r20-recovery-red-summary.json. This is software return injection,
NOT real busfaults, DMAquiescence, lock-race or buffer-ownership proof.

Next: make reset/create/CSS/sensor-restart failure failclosed; verify CSS/ISP
DMAquiescence before returning heldbuffers; ensure SOF/CSI/DFS/parameters and
VB2wakeup, one MCpipeline stop by its actualowner (worker must not double-stop
the later VB2stop). Normalstop still ignores atomisp_reset and onlywarns on
stream-recreation failure; review that same contract. A flag-only mockgreen
is insufficient for hardware safety. No current kernel/device fault injected.

Other scope remains: all-scene AE/AWB/AF/NR/color/optical parity, GUI/player/
rotation/cancel, stilllatency/rearphysical15fps, native fractional gain design,
headlessboot/highrates/compat32/MediaRequests/DSP/otherhardware, flashimagebuild.
