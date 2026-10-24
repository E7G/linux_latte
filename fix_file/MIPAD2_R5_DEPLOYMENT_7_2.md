# MiPad2 7.2 r5: physical AIF2 graph deployed and power gating verified

## Status: 2026-10-24 (CONT27)

Image source: `8bc6bf83ae3f3104a5649036c013bac4a0155bdd`.
Running release: `7.2.0-mipad2-integrated-r5`, after exactly one guarded warm reboot.
The physical RT5659 AIF2 transmitter -> stereo TFA receiver topology is now in
the complete stock-backend image, not a runtime route overlay. Both permanent
codec and board PLL dependencies remain. No generic ASoC-core graph hack,
register replay, force-on clock, resume-repair script or factory-DSP activation.

## Later recording result: cadence FAILED, not full video qualification

Subsequent normal foreground 1080p recordings completed and decoded, but front
and rear failed the existing cadence gate (26 and 12 gaps >50 ms). Earlier
electrical/native tests below do not qualify encoded recording. See
[preserved failure and investigation scope](MIPAD2_R5_RECORDING_REGRESSION_7_2.md).

## Build and protected deployment

W=1, Clang21, thin LTO built bzImage and 31 modules, using the exact r4 config;
all seven protected r4 build artifacts remained unchanged. Three pre-existing
LTO stack-frame warnings remain (AtomISP 1128, poll 1064, zstd 1352 bytes).
All 31 module CMS signatures verified. Native ALPM package query/read-only
preflight passed; the local package is not PGP-signed and was not installed
through pacman. The device uses the separately staged isolated payload.

Running image/config and loaded-driver identities matched. Final post-test
audit rehashed 2,214 protected installed files and all 48 manifest payload files;
none changed. All 35 private diagnostic aliases retained their original data
and access restrictions. 51 discovery smoke checks passed, including both
native sensor bindings and focus actuator. Rescue default remains
`mipad2-bqdiag1`; the single-use entry was consumed. This is not S5 proof.

## Actual electrical gating, not just a logical DAPM graph

The read-only probe reads each component's own regmap and bypassed hardware.
Only digital-zero playback was used; captured microphone samples went directly
to `/dev/null`, without saving or exporting audio.

| Phase | RT5659 PLL | AIF2/I2S2 | Both speaker amps |
|---|---|---|---|
| Idle | off | off | power-down |
| Digital-zero playback | on | on | ready |
| Stopped and settled | off | off | power-down |
| Mic only | on, needed for capture | off | power-down |
| Mic + digital-zero playback | on | on | ready |
| Mic still running after playback stops | on | off | power-down |
| Final idle after mic stops | off | off | power-down |

This confirms the old idle cycle and false mic-to-speaker power path are absent
in these cases. It does not measure wall power, acoustic output, microphone SNR
or headset behavior. Mic source/mute/volume and UCM remained unchanged.

## Two independent RTC cycles on the same unmodified r5 boot

| Cycle | Requested sleep | S0I3 increment | OS-estimated suspended time |
|---|---:|---:|---:|
| 1 | 12 s | 12088000 us | 11.474777256 s |
| 2 | 12 s | 12176896 us | 11.520012606 s |

PLL/I2S/Platform Clock were off before and after sleep and after playback
settled; zero playback powered the PLL and both ready amps as expected. The
second cycle followed both camera and microphone/duplex regressions. No route
repair or reboot between cycles. Both traces had zero overruns, no new fault
markers, cleared RTC alarms and complete probe/trace cleanup. USB was attached;
IRQ9 is shared by ACPI/INT0002. Not pristine untethered power measurement or
unique wake attribution.

## Camera regression and final state

Both cameras passed four 120-frame phases each at 1920x1080 NV12: 960 frames,
zero sequence discontinuities or buffer errors, with same-owner stop/restart,
close/reopen and observer EBUSY checks. Maximum interval: rear 33.895 ms,
front 34.061 ms. Original input, video shape, both sensor crop/format and
captured controls were restored in dependency order. This is native capture,
not encoded Snapshot recording or proof of source-frame conservation.

After the second RTC cycle, each camera delivered four more default
1280x720 YU12 frames without S_FMT/S_PARM/control writes. Samples were deleted
only after passing; no pixels were exported. Sensors and ISP ended runtime
suspended with usage zero. All five device jobs ended inactive/dead, exit 0;
all PCM closed, probes unloaded, traces removed and RTC cleared. No new
panic/BUG/WARNING/GPU/DDR/ISP/stop-reset fault markers or failed units.

Serial logs remain tablet-private (66,762 bytes). No early r5 banner appeared
on the late USB console; SSH/proc/config/image/module checks independently
established identity. Read-only unsigned diagnostics raised taint 1088 -> 13376;
unload does not reset it. Retained volatile differences include RT5659 0x82
active cache 12288/hardware 12289 and idle TFA status cache 2141/hardware 2653.
Do not claim all 33 cached/hardware registers match.

Final health: 100% battery, maximum thermal zone 52 C, 2,363,027,456 bytes free.
Thermal/no-idle guards active; requested auto-lock, DPMS and automatic suspend
remain off, with manual authentication unchanged.

## Remaining qualification

Normal encoded app recording on this r5 topology, fresh human acoustic/stereo,
headphones, controlled mic/optical/rotation, S5 reliability and long-run/thermal
or physical failed-reset DMA-fault injection remain open. Factory DSP remains
unselected, with firmware/profile/UCM/calibration-MTP policy and alternate-build
lifecycle still unqualified. No full OS image or Android/Windows parity claim.

[Scalar hashes and bounded qualification](tests/mipad2-7.2-r5-deployment-summary.json).
[Root cause, preserved r4 failure and host regression](MIPAD2_AIF2_IDLE_GRAPH_7_2.md).
[Prior r4 normal encoded recording, not an r5 result](MIPAD2_R4_CAMERA_RECORDING_7_2.md).
