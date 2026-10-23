# Factory CoolFlux candidate: real 7.2 code port, not hardware activation

This advances beyond the [observed active bypass backend](MIPAD2_AUDIO_RUNTIME_7_2.md).
The default/current tablet remains7.2r3 with built-in tfa989x. No module unbind,
firmware write, reboot, audible/nonzero PCM, calibration or device-config change.
Code is a necessary candidate port, not an easier bypass substitute or OEM parity.

## Compile failures actually reproduced and corrected

The inherited factory source failed a complete W=1 external-module build against
the real7.2r3 headers/Module.symvers: removed CBS/CFS and CBM/CFM names,
snd_soc_kcontrol_component and snd_soc_component_get_dapm calls. It is now using
current CBC/CFC and CBP/CFP clock-role symbols (same bit meanings), snd_kcontrol_chip
for ordinary mixer controls and snd_soc_component_to_dapm. No guessed compatibility
macros or suppressed compiler errors. Intermediate API-only and final complete
three-object module builds succeed with Clang21, thinLTO, W=1 and no warnings.

Final candidate ELF **b21af433e6d37da814cbead99cb5c76bc1b477d578632eb74268e51721590808**,
1282640bytes, vermagic7.2.0-mipad2-integrated-r3; modinfo declares default firmware
tfa98xx.cnt and existing i2c:tfa9890 aliases. Actual tablet modaliases match those
aliases; no speculative ACPI alias change. All nine codec input files are hashed
and match the compiled scratch copy. Original r3.config/Module.symvers/vmlinux/
bzImage/kernel.release hashes remain unchanged. No full r4 kernel/image built.

External module compilation forces the M target using r3's symbol set; it does
NOT authorize co-installing both backends or prove a full candidate Kconfig build.
Build output was not copied to or loaded on the tablet.

## Correct board namespace and per-device controls

The current machine already assigns Left/Right name_prefix, expects Left/Right OUT
and Left/Right HiFi Playback. Inherited factory OUT Left/OUT Right and per-I2C
stream names did not match that graph. Factory widgets now use local OUT and
HiFi Playback, receiving exactly one board prefix. Address34/37 validation kept.

Factory mixer controls now use immutable local Profile/Master Volume/Stop names,
with a devm copy and profile pointers per instance. No global mutable name buffers
or writes to shared template private_value. Allocation and ALSA control-registration
errors propagate rather than reporting a successful partially configured probe.
When selected, controls become Left/Right Profile, Master Volume and Stop. This
is a deliberate factory ABI; fake Amp Input compatibility would risk bypassing
DSP again and is not supplied. **Existing UCM8 AmpInput profile is not compatible**.

The new ASan/UBSan host fixture executes the actual production component probe,
widget/control initializers and stream initializer using narrow ASoC namespace
and allocation stubs. Two prefixed instances, isolated profile storage and six
failure paths (firmware/address/widget/route/allocation/control) pass. The exact
API-only old topology fails the intended first board-ABI check. This is not a
real kernel DAPM clock/power or on-chip DSP proof. Existing mute/worker/start
regressions and38stock-format cases pass; stale host API/constants were updated.

```sh
python3 fix_file/tests/mipad2-tfa-probe-topology-test.py
python3 -O fix_file/tests/mipad2-tfa-probe-topology-test.py
python3 fix_file/tests/mipad2-tfa-mute-worker-test.py
python3 fix_file/tests/mipad2-tfa-start-test.py
python3 fix_file/tests/mipad2-tfa-format-test.py
```

Only the new probe fixture uses explicit always-on requirements/C CHECK under-O.
Older source-string guards run normally; optimized execution is not claimed to
strengthen their optional assertions. Legacy live-script string checks do not
make the old6.14 driver-switch runner usable for this changed factory ABI.

## Real Kconfig alternative selection bug

Original `depends on !SND_SOC_TFA989X` allowed both drivers=m because tristate !m=m.
That was reproduced with real olddefconfig before changing it. Dependency now
requires stock=n. Real solver matrix: requested stockm/factorym ->m/n;
stocky/factorym ->y/n; stockn/factorym ->n/m. Default stock config untouched.
A separate factory-r4.config resolves correctly, but no bootable kernel from it
has yet been built. This removes ambiguous alternative-driver module selection;
it is not evidence that an activated factory profile already works.

## Android/Windows inputs actually inspected

Primary Intel-Latte Android source pinned at
[d2afb1de](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/sound/soc/codecs/tfa98xx.c),
not an unrelated ARM audio implementation. Its older codec/stream conventions
were compared with this branch's current prefixed machine graph.

Local factory container exactly matches the earlier tablet copy:5133bytes,
SHA83709da84f22b5c0ff1f7568478b3ecbfc1c1c29bc3814a8be8a64426f3c2c2a.
Packed header/CRC verified, two device entries left0x34/right0x37 on bus1,
header profile count6. That does not yet prove correct per-profile calibration,
sample-rate choice or on-chip execution. No container bytes changed or uploaded.

The existing four-part Windows backup was read via a temporary joined copy and
bsdtar INF-to-stdout; all original hashes unchanged, temporary join removed, no
driver binary executed. oem27.inf identifies Intel SST12/11/2015 version
604.10135.3202.10118, including Xiaomi A3 subsystem1D721502 and TDM loopback.
This provides board/platform context, not proof of a matching TFA firmware,
calibration or CoolFlux behavior. No Windows-DSP equivalence is invented.

## Required before real factory playback / completion

Keep default stock backend and defer_dsp_start=true until proper candidate bring-up.
Needed: DSP-aware UCM complete-pair/profile/volume/Stop policy (not the bypass
AmpInput sequence), confirmed C2C/no_pcm clock/start/stop lifecycle, firmware profile
and calibration-write policy, whole candidate kernel/package/rescue/serial gates,
then real deferred probe and bounded zero PCM before human-ready listening.
No old module hot-switch or forced raw I2C scripts were used.

[Machine-readable build/test/vendor evidence](tests/mipad2-7.2-factory-dsp-port-summary.json).
Current tablet postflight retains stock tfa989x/Left0Right1/closedPCM,686 protected
files and35private aliases unchanged, no new kernel faults. Raw kernel/UART/pointer
and media evidence stays tablet-private. Old freeze/failed-reset DMA, full image,
optical/acoustic/long-stability goals remain open; no default/OEM/task promotion.
