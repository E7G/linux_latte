# MiPad2 7.2: PLL power dependency across suspend/resume

## Status (2026-10-24, CONT22)

The previous conditional I2S-to-PLL fix restored two audible tones, confirmed by
the user at unchanged volume. It still lost PLL power after suspend. This follow-up
reproduces that failure, identifies the clock-selection ordering, and validates
an additional board supply dependency through two consecutive RTC resume cycles.
No new audible tones were played this turn. No new kernel was installed or booted.

## Root cause and change

`platform_clock_control(POST_PMD)` selects RC for idle/jack detection. On resume,
DAPM computes supply power before `platform_clock_control(PRE_PMU)` selects PLL1.
The codec's `is_sys_clk_from_pll()` sees RC during that computation, so conditional
I2S routes alone cannot request PLL power. Switching GLB_CLK later does not redo
that completed supply power check. This is not a stale register-cache diagnosis.

The board now adds `{ "Platform Clock", NULL, "PLL" }`. All four board endpoints
already depend on Platform Clock; all active board paths use PLL1. The dependency
is board-specific and does not alter generic RT5659 MCLK/RC behavior. It uses
normal DAPM power management, not force-enable pins, register pokes, cache replay,
resume scripts or delayed repair workers. PLL can turn off with the supply.

## On-device comparison

All tests used unchanged `7.2.0-mipad2-integrated-r3`, stock TFA989x bypass,
Left/Right Amp Input 0/1, the existing conditional route overlay, and digital-zero
PCM only. Raw ftrace/kernel logs remain root-private on the tablet. Only register
values, event kinds and aggregate counters were exported. No trace overruns.

| Case | S0I3 increment (us) | Post-resume RT5659 0x65 | Both TFA status |
|---|---:|---:|---:|
| audio-pm | 11850144 | 0x0000 | 0x0a5d/0x0a5d |
| board-pll-pm | 11713056 | 0x0040 | 0xd85f/0xd85f |
| board-pll-pm-repeat | 11590976 | 0x0040 | 0xd85f/0xd85f |

Baseline trace: Platform Clock off -> GLB_CLK RC -> PLL power zero -> resume
I2S1/I2S2/Platform Clock on -> GLB_CLK PLL1, but no PLL power-on event/write.
Both corrected traces also contain the PLL power-on event and a 0x65=0x0040
write. The intermediate 0x65=0 remains, so the fix is not keeping PLL on throughout
suspend. Both corrected captures show hardware PLL lock and amplifier analog ready,
including during zero PCM; all three tests returned to closed PCM and idle cameras.
No new kernel fault markers. The shared wake IRQ does not uniquely identify a source.

Actual RT5659 register 0x82 hardware bit 0 differed from its cached value in healthy
captures; volatile amplifier status also changed between baseline idle reads.
These differences are retained, not mislabeled as proof of cache corruption.
Probe-time calibration's whole-register 0x65 writes were inspected; they are not
called by the codec resume callback and were not used as a speculative fix.

## Source/build regression checks

- Production machine module: W=1, Clang 21, thin LTO and modpost passed, no warnings.
- Temporary board overlay uses exactly the production route and card DAPM context.
  First overlay compile exposed the 7.2 pointer-valued card DAPM API; corrected to
  `snd_soc_card_to_dapm()`. Failed build log retained; no failed module loaded.
- `tests/mipad2-board-pll-pm-test.py` executes extracted production supply traversal,
  power-check cache and PLL predicate in a small C/ASan/UBSan graph fixture. It
  reproduces RC-before-PRE_PMU failure, verifies the new route, tests all four
  selectors and 100 off/on walks. Normal and Python `-O` pass. The actual prior
  machine source fails the missing-dependency guard in both modes as intended.
- Original r3 config, symvers, vmlinux, bzImage and release hashes unchanged.
- Exact source/module hashes and scalar results: [summary](tests/mipad2-7.2-board-pll-resume-summary.json).

## Remaining work / live state

`mp2_pll_route` and `mp2_board_pll` remain intentionally loaded; neither autoloads
on boot. Read-only probe unloaded, all tracing instances removed, RTC cleared,
all three test units terminal. Kernel taint remains 13376 from unsigned external
diagnostics. Stock bypass is still selected; factory DSP/calibration is untouched.

This is runtime graph validation, not a full integrated-image/cold-boot pass.
Next: build/install the production codec plus board routes in a new 7.2 image,
preserve the rescue entry, then cold boot/resume/audio checks. Idle audio graph
power, full acoustic/stereo/mic/headphone qualification, factory DSP/UCM/MTP policy,
the prior long-run hang and the wider camera/PM/OEM-equivalence goal remain open.

See also [original no-sound and preserved resume failure](MIPAD2_PLL_DSP_LIFECYCLE_7_2.md).
