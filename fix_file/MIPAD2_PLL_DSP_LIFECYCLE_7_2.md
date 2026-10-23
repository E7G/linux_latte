# 7.2 sound restored: missing serial-clock PLL dependency

## Actual failure and controlled runtime correction

The tablet remains 7.2.0-mipad2-integrated-r3, boot e41b808f-b6f2-4a53-a3b0-8d5eb1046bf6.
Its active amplifier driver is still stock tfa989x, **CoolFlux DSP bypass**, not the
factory candidate. Before correction the human heard neither short tone, although
PipeWire returned success and DAPM described powered speaker widgets.

A read-only diagnostic used the owning regmap and regmap_read_bypassed, not forced
I2C. The 33 sampled cached/hardware values agreed both idle and during digital zero:
this does NOT support blaming stale cache for this failure. RT5659 selected PLL1
SYSCLK but PWR_ANLG_3 (0x65) was 0; both TFA status registers were 0x0a5d, without
PLL lock or analog readiness. Simply cycling Ext Spk did not recover them.

DAC_REF -> I2S2 digital loopback bypasses the ADC/DAC filter widgets that previously
owned all PLL dependencies. All three serial ports now depend directly on PLL,
conditionally through the existing is_sys_clk_from_pll predicate. MCLK/RC operation
does not acquire this dependency. No fixed PLL-enable register pokes, cache replay,
forced I2C access, OTP programming or volume increase are used.

A temporary module overlaid the **exact three production routes and predicate** on
the existing card. RT5659 0x65 became 0x0040 and both TFA statuses 0xd85f, with PLL
lock and analog readiness. Replaying the exact original stereo WAV at the same
stream volume0.5 and unchanged sink integers30801/30801 restored both audible tones;
the human explicitly confirmed both. This establishes a real sound-path correction,
not acoustic quality, independent left/right separation, or factory DSP equivalence.

The temporary mp2_pll_route module is intentionally retained for current sound.
It has no boot autoload/persistent install: **rebooting the original r3 image loses
this runtime overlay**. The permanent production rt5659.c patch is separately built
and linked, W=1/Clang21/thinLTO; it is NOT yet installed as a new boot kernel.
The r3 config/symvers/vmlinux/bzImage/kernel.release five hashes remain unchanged.

The temporary read-only diagnostic is unloaded. External unsigned module loading
changed kernel taint1088 ->13376; those taint bits remain until reboot. This was a
real diagnostic state change, not an untouched kernel. Raw kernel traces remain
private on the tablet; only register/value scalar metadata is exported.

## Resume scope actually exercised

With the overlay loaded, one requested12-second RTC s2idle cycle returned normally:
PMC S0I3 +12205376us; CLOCK_BOOTTIME-minus-MONOTONIC estimated11.640283558s asleep.
These are different measurement windows, not equal-duration claims. IRQ9 is shared
acpi/INT0002, not uniquely attributed. L/R selectors remain0/1, PCM closed, sensors
and ISP suspended usage0, fault deltas0 and RTC alarm clear. A fresh post-resume
digital-zero run plus owning-regmap hardware reads **FAILED the audio clock gate**:
RT5659 0x65 returned to0, both TFA status0x0a5d, despite the overlay still being loaded.
The PM runner's resume-gates-passed means OS/residency/route checks only; it did NOT
include those later physical clock reads and is NOT a post-resume audio pass.
An initial report-generation readiness check failed rather than publishing success.
The exact failed records are preserved. One intentional overlay unload/reload restored
PLL power and both amp PLL/analog readiness, confirmed by a new zero-PCM/read-only
probe. No automatic resume workaround was installed, no second suspend was run,
and **no post-resume/reapply human hearing confirmation was collected**. The current
sound-path correction is real but its resume lifecycle is still unresolved.

## Factory DSP lifecycle correction, still not active

The current Dummy-TFA989x links are no_pcm graph anchors, unlike the separate C2C
RT5659 AIF2 link. Their PCM trigger/mute callbacks do not receive that link's DAPM
events. Factory NXP Output Mixer now has POST_PMU/PRE_PMD events calling the existing
worker-draining lifecycle helper. Actual7.2 core sequencing places the mixer after
clock/AIF/DAI setup on power-up, before their removal on power-down. A supply event
would be too early. defer_dsp_start=true remains completely passive at these edges.

Production factory module full three-object link and modpost pass; SHA
55fc45a47f76f356e86250ca4aa5fb82ddddd822e85a68810406b3a52a7ef26b.
It is NOT loaded/bound. DSP-aware UCM, whole alternative-config kernel, real DSP
calibration/clock/recovery and physical output remain unqualified.

Host regressions: eight existing/new positive commands plus two intended missing-hook
negative controls; PLL route/predicate adds two positive and two intended old-source
negatives. New tests use explicit Python requirements/C CHECK and ASan/UBSan, normal
and-O; older assertion-based guards run normally only.128 actual-selector cases cover
PLL/MCLK/RC/reserved SYSCLK and unrelated bits. These are not kernel stress tests.

## Factory container metadata, not guessed volume policy

The pinned5133-byte container/outer CRC is unchanged. Each amp has three profiles:
musicL/speechL/bypassL and musicR/speechR/bypassR. Music/speech VP2 files have just
one volume step, sample-rate code8 (48000Hz in the driver table); bypass has no VP.
Their nested size field is zero despite valid nested CRC: descriptor sizes are449.
An initial metadata script's assumption that all nested sizes equal descriptors
was rejected; zero sizes were reported, not silently repaired. Speaker payloads
are left/right-specific. Do NOT invent multi-step volume control, choose bypass as
the final DSP path, or infer safe OTP calibration from container presence. The
factory cold-start code can program calibration MTP; policy is still required
before activating it. No such writes were requested by this correction.

## Next required

Build/install a fresh7.2 integrated kernel retaining rescue/serial gates, then prove
sound without the temporary overlay after reboot and resume. Keep factory backend
unselected/deferred until its UCM/profile/calibration policy and complete build are
qualified. Idle clock residency/power, microphones/headphones, previous long freeze,
failed-reset DMA and full OEM image qualification remain open.

See [scalar summary](tests/mipad2-7.2-pll-dsp-lifecycle-summary.json) and the
[kernel DAPM documentation](https://docs.kernel.org/sound/soc/dapm.html).
