# MiPad2 7.2: correct the AIF2 speaker transport graph

## Status update (2026-10-24, CONT27): r5 deployed; bounded electrical tests pass

The complete stock-backend r5 image now validates idle/playback/mic-only/duplex
hardware gating and two RTC cycles, without runtime route overlays or register
replay. Native dual-camera 960-frame regression and final protected-file audit
also pass. See [r5 deployment and limits](MIPAD2_R5_DEPLOYMENT_7_2.md).
No fresh acoustic, measured wall-power, factory-DSP or full OEM-parity claim.

The root-cause and candidate/build sections below preserve their CONT25 scope;
their historical "not booted/not installed" statements describe that checkpoint,
not the subsequent CONT27 r5 deployment. Remaining tests below are not all done.

## Observed defect and references

All three public PCM substreams were closed and all four RT5659 DAI streams
reported inactive. Nevertheless, AIF1 Playback, AIF2 TX, both C2C directions,
I2S1/I2S2, PLL, Platform Clock and both speaker paths were logically on.
The captured connected graph contains this exact cycle:

```
AIF1 Playback -> AIF1RX -> IF1 DAC1 -> IF1 DAC1 L -> DAC L1 Mux
 -> DAC1 MIXL -> DAC_REF -> IF2 ADC Mux -> IF2 ADC -> IF2 ADC Swap Mux
 -> AIF2TX -> AIF2 Capture -> Codec AIF2 Port-capture -> AIF1 Playback
```

This was parsed from actual connected DAPM paths, not inferred from a register
cache mismatch. Raw graph/kernel logs remain tablet-private; exported data is
widget names, types, state and edge metadata. No fresh volatile register sample
or wall-power measurement is claimed by that logical graph snapshot.

Actual 7.2 `snd_soc_get_stream_cpu()` reverses the CPU stream for C2C links.
Modelling the codec's internal AIF1 RX -> DAC_REF -> AIF2 TX as an external,
bidirectional AIF1/AIF2 C2C link therefore adds the reverse edge above. The real
endpoint walker returns 1 when revisiting a walking path, so this bad board cycle
looks connected even with no active DAI. The generic core is not patched: its
cycle handling also serves legitimate graphs. The old playback half separately
connects AIF1 Capture -> AIF2 Playback -> speaker widgets, allowing an unintended
mic-source path when the Int Mic pin is enabled.

The [Android board reference](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/sound/soc/intel/board/cht_bl_dpcm_rt5659.c)
uses the legacy AIF1/AIF2 link and 48 kHz S16 stereo external amp parameters.
That legacy topology must not be copied without accounting for the current
core's directions. Windows INF/binary references identify the device family;
Windows implementation source is not available here and equivalence is not
claimed. The [upstream C2C documentation](https://www.kernel.org/doc/html/latest/sound/soc/codec-to-codec.html)
describes external codec-to-codec transport; actual 7.2 implementation and the
observed device graph are the decisive references for this port.

## Candidate changes

- Replace the synthetic internal AIF1/AIF2 link with the physical external bus:
  `rt5659-aif2` Capture/TX on the CPU side -> both TFA Playback/RX DAIs.
- Use one playback-only multi-codec C2C link, fixed 48 kHz S16 stereo.
  Amps consume BCLK/LRCLK (`CBC_CFC`); the core configures the codec CPU side as
  provider. The SSP2/AIF1 backend remains S24, without unrelated fake C2C
  parameter programming of AIF1. Both existing codec and board PLL dependencies
  and late DAC_REF DAPM mux synchronization are preserved.
- Remove manual amp routes from the wrong AIF2 receiver widget and redundant
  graph-only dummy amplifier links. The real C2C core now creates transmitter
  to receiver paths and invokes the appropriate hardware-parameter callbacks.
- Real C2C links invoke `mute_stream`, including power-down. Factory deferred
  safe-probe previously guarded only its output-mixer event; its mute callback
  could still write DSP stop registers. Guard digital mute with the same defer
  setting. Stock remains selected on the tablet; no DSP/firmware/MTP programming.

## Builds and regressions

Production machine module and all three factory module objects compiled W=1,
Clang21, thin LTO, link and modpost without warnings. Neither module was loaded
or installed; five protected r4 build hashes remained unchanged. This is not a
full alternate-Kconfig or factory-DSP hardware qualification.

Nine host tests passed normal and Python `-O` (18 positive runs); actual prior
machine and factory source failed four intended negative controls. The precise
old-machine failure is idle cycle power; the old factory failure is attempting
DSP stop with clocks absent while deferred probing should be passive.

`tests/mipad2-aif2-speaker-graph-test.py` extracts six actual production functions:
endpoint traversal and its wrappers, generic power check, CPU-stream direction,
and C2C PRE_PMU parameter setup. C/ASan/UBSan fixtures reproduce the old cycle
and false mic path, check the corrected idle/playback/capture/duplex/headphone
graph across 100 walks, and verify AIF2 capture plus both amp playback callbacks
with the fixed parameters. Current core adds a shared source edge per codec;
the fixture preserves that duplicate and tests the actual callback counts.
It is a minimal signal graph, not the complete kernel scheduler or hardware.

Factory tests now check real C2C receiver/prefix ABI and both C2C mute plus
output-mixer events, including default passive probe, quick stop/reopen, stop
error propagation and worker drains outside the initialization mutex. They do
not execute CoolFlux, calibration or a real timing/race/power sequence.

Initial fixture failures (missing trace no-op; a baseline expectation that
incorrectly disabled the mic source) are retained. Production code was not
changed to make those shim assumptions true. The revised test distinguishes
the independent legacy feedback and mic-to-speaker paths.

## Required device validation / remaining work

Build a complete new stock-backend image, preserve r4/rescue and private serial
diagnostics, then test the real initial graph and hardware clock state. **Idle
should power down** PLL/I2S/amps; during zero PCM they must become ready, and
after stream close return off. Do not reuse r4 tests which required ready
amplifiers even at idle: that would reject correct gating and encourage a bad
force-on workaround. Include mic-only, duplex, sleep/resume, reopen, headphones
and a fresh human acoustic check when available. No live codec unbind or forced
clock/register-off experiment is part of this candidate.

Factory default defer remains true. Full mutually exclusive configuration,
firmware/profile/UCM and calibration-MTP policy and real lifecycle validation
are still required before factory activation. Long-run/thermal/DMA-hang, S5,
controlled mic/optical/rotation and complete Android/Windows parity remain open.

[Scalar witness, hashes and test results](tests/mipad2-7.2-aif2-speaker-summary.json).
[Existing r4 recording/resume evidence](MIPAD2_R4_CAMERA_RECORDING_7_2.md).
