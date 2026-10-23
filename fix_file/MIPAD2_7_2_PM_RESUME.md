# 7.2 r3: two actual s2idle/S0I3 cycles and native camera restart after each

This is bounded hardware evidence, **not** full MiPad2/OEM suspend qualification.
Actual runtime7.2.0-mipad2-integrated-r3, C/build20f0304f, same boot throughout.
No kernel C patch/build/reboot, default camera promotion, audio playback, sensor
fault injection or permanent configuration write for these tests. Previously
installed immediate thermal escalation source remains unchanged and active.

## Actual power transitions

Fresh gates checked s2idle, pm_test=none, RTC wake enabled/no existing alarm,
idle sensors/ISP usage0, no camera owner/app, healthy kernel markers, guards,
disk floor, battery>=30% and temperature<65C. Root asynchronous units persist
through temporary SSH loss. Each requested12s RTC suspend ran exactly once;
host waited18s before observing rather than sending SSH probes during sleep.

| Cycle | Serial reader | PMC S0I3 increase | OS estimated suspended | Unit / kernel faults |
|---|---|---:|---:|---|
| First | Live read-only USB gadget reader | 12.020448s | 11.461734s | exit0 / none added |
| Second, after camera capture | Reader closed, USB still attached | 11.590176s | 11.038792s | exit0 / none added |

PMC and OS-clock values deliberately remain separate. [PMC driver](../drivers/platform/x86/pmc_atom.c)
reads32-bit counters and shifts by5, [32us units](../include/linux/platform_data/x86/pmc_atom.h).
PMC samples bracket a wider interval, including a3s post-resume wait; OS estimate
is CLOCK_BOOTTIME minus monotonic elapsed around rtcwake. These are not identical
windows, so no inferred clock calibration, timestamp rewrite or exact equality.
Both exceed the stated8.4s minimum; RTC alarm cleared, boot unchanged, both units
inactive/dead/MainPID0/exit0 and sensors/ISP suspended usage0 after each return.

Wake IRQ9 is shared `acpi,INT0002`, not unique proof of an RTC cause. First raw
wakeup-source table only showed charger active/event+1 and wakeup_count0; don't
mislabel charger as the cause. Second test additionally measured ACPI fixed-event
counter `ff_rt_clk`+1, supporting an RTC event while retaining shared-IRQ scope.
Kernel suspend entry/exit and no abort/error were independently observed in the
first private log. No untethered/long-sleep or battery-drain claim.

First serial reader was proven live by native process status and fresh tablet
outbound marker before dispatch. Two opens/13 USB re-enumeration retries,1202B
received, marker2, no matched panic/BUG/WARNING/DDR failures. Reader explicitly
stopped and uploaded raw bytes to root0600 on the tablet; never written as a raw
host file or used for input commands. This is not complete firmware/early-boot
coverage; no reboot occurred. A host controller syntax error was caught before
unit staging, fixed, then one actual first-cycle dispatch; no repeated suspend.

## Native cameras after EACH return

Exact [published raw fixture](tests/mipad2-7.2-r3-lifecycle-device-test.c), source
21d2778795f0017ca788c6320e2724d13e7b195cb8abde42dfef19d87fa39cca,
host-compiled ELF34d4cfd3268fc65c6e8ed1b4fa46634b68de560fd35ee5835c3ec9afca2a8398.
Both cameras negotiated1920x1080NV12. Each camera/round had four120-frame phases:
three STREAMOFF/ON owner reuses and a final owner close/reopen, with independent
nonowner ioctl rejection and spectator close during active capture.

| Cycle | Rear max interval | Front max interval | Frames / negative ownership ops |
|---|---:|---:|---:|
| First return | 33.981ms | 33.973ms | 960 / 32 |
| Second return | 33.904ms | 34.098ms | 960 / 32 |

All1920frames,64negative checks, zero sequence discontinuities or buffer errors,
all whole-phase intervals<=50ms and sums consistent. Existing strict source
oracle, not C exit0 alone, checks measured scalar phases. No pixels copied or
saved, no encoded MP4, optical identity/quality, live-preview or acoustic proof.
Controllers snapshot fresh formats/crops/controls including vertical blanking,
restore crop FIRST then format/binning then controls with readback, and restore
original input/global output format. All readbacks pass and no children remain.
Failed-reset DMA fencing is NOT exercised by successful normal restarts.

## Current postflight and open scope

686 protected installed files unchanged; exact thermal guard source and both
installed UCM8 sources match separately,35 private aliases/bytes/access unchanged.
No kernel panic/BUG/WARNING/Oops/GPU/DDR/ISP/reset markers or failed units;
no camera/GStreamer clients, both guardsactive, sensors/ISP suspended usage0.
Native compositor read-only control responds, internalDSIconnector connected and
backlight255/255/on; **visual display content not human verified**. User-selected
automatic lock/DPMS/suspend remainOFF; manual locking/login untouched.

[Scalar evidence](tests/mipad2-7.2-pm-resume-summary.json) and bounded host tests
do not replace the actual hardware transitions above. All raw media/per-frame
metadata/kernel/serial/pointer traces remain tablet-private. No media removed.
Prior556ms normal-app failure, interrupted rear,3.5h hard freeze, failed-reset
DMA quiescence, optical quality, actual7.2 audio/mic/headphones, S5 and complete
image/rootfs ownership/ABI remain open. No Android/OEM parity or task completion.

## Reproducible bounded host oracles

```sh
python3 fix_file/tests/mipad2-7.2-pm-resume-summary-test.py
python3 -O fix_file/tests/mipad2-7.2-pm-resume-summary-test.py
```

Ten scalar consistency/negative tests reuse the existing raw-fixture strict gate,
rejecting exit0 with no residency, changed boot/live unit/child, kernel faults,
active PM, sequence gaps, wrong native size or failed restoration, nonfinite
measurements and leftover alarm. They retain explicit shared-IRQ and non-OEM
scope. These are host oracles, not additional physical suspend/codec tests.
