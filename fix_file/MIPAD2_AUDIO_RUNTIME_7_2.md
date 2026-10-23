# 7.2 r3 actual audio: runtime stereo route corrected, OEM DSP still missing

Actual same7.2.0-mipad2-integrated-r3 boot, C/build20f0304f. UCM8 files already
matched published source, but that did not establish correct live routing.
Current PipeWire1.6.8 / WirePlumber0.5.17 / ALSA1.2.16 stack exposed the normal
HiFi(IntMic,Speaker) profile, with **both Left Amp Input and Right Amp Input=Left**.
The existing UCM8 Speaker sequence requires Left/Right respectively.

## Runtime correction, not a new driver or profile-file patch

With all PCM endpoints closed and no active playback/capture stream nodes,
temporarily muted the exact normal speaker sink, restarted only WirePlumber,
then verified the new device applied Left0/Right1. Restored original exact Pulse
integer sink/source volumes, mute flags, default sink and profile. Denial settings
bytes unchanged, PipeWire core not restarted, new UCM control errors0. No PCM
playback/capture started for this reload. The long-lived manager having loaded
older config is plausible, not uniquely proven from one generic old UCM log error.

This matches WirePlumber's role in creating ALSA devices and using UCM when
available ([official ALSA monitor documentation](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html)).
Read-only disk parser success must not be described as a running-service reload.
Restart may disrupt clients; the measured operation first required no clients.

One subsequent12s s2idle check retained ALSA selectors0/1 before/after, empty
alarm, same boot, no kernel faults and closed PCM endpoints. PMC S0I3 increased
11.602976s; OS estimated suspended11.067255s in a different measurement window.
IRQ9acpi/INT0002 remains shared, not unique RTC attribution. This is ALSA-visible
selector retention, **not independent on-wire register/signal verification**.

## Digital-zero stream: startup observed, premature idle gate retained

Played one source containing exactly288000frames/6s/S16LE48kHz stereo, all1152000
PCM bytes ZERO (source digest in scalar receipt), through the normal speaker
PipeWire sink. No nonzero/test tone or microphone capture. ALSApcm0p RUNNING was
observed; pw-play exited0, selectors remained0/1 before/during/after, no new
kernel/ASoC/regmap/xrun markers and original sink volume/mute unchanged.

The original controller classified this check failed because an endpoint was
still open at only3s after EOF. **That original failed receipt is retained**.
A later read of the SAME playback found all PCM endpoints closed and node
SUSPENDED, without replay. Installed suspend-node.lua defaults to5s when no
session.suspend-timeout-seconds property is specified; this node had no override.
Thus3s was a premature check. Exact actual close latency was NOT measured; do
not claim closure within5s or silently rewrite the original failed snapshot.
These facts demonstrate digital-zero flow, not audible output or speaker quality.

## Major remaining audio fidelity gap: active driver bypasses DSP

Both actual amplifiers are bound to built-in **tfa989x**, CONFIG_SND_SOC_TFA989X=y;
no loadable TFA candidate modules are installed. [Active driver source](../sound/soc/codecs/tfa989x.c)
explicitly configures CoolFlux DSP bypass and uses regcache. Present tfa98xx.cnt
(5133bytes, SHA83709da84f22b5c0ff1f7568478b3ecbfc1c1c29bc3814a8be8a64426f3c2c2a)
is not proof of loading: this driver does not load the vendor container.
The separate tfa98xx-xiaomi source in the tree is NOT the active backend.

Consequently zero DSP-timeout messages cannot prove a working vendor DSP when
that path is not executing. Bypass does not deliver vendor firmware tuning,
calibration/protection/profile equivalence merely because PCM runs. RT5659/system
mixers still expose volume control; don't interpret the generic bypass comment
as proof that all desktop volume is absent. Proper vendor DSP integration,
firmware/board-DAI mapping and physical listening remain real work, not replaced
by this narrower selector fix. No speculative module unbind/hot switch was done.

## State and provenance

[Scalar receipts](tests/mipad2-7.2-audio-runtime-summary.json) retain both the real
correction and negative idle snapshot. All raw mixers/PipeWire dumps/journals,
kernel logs and hardware/pointer evidence stay tablet-private. Generated zero WAV
contains no captured audio. UCM source,686 protected files and35 private aliases
unchanged; actual thermal guard source matches separately. Both guardsactive,
no failed units/active camera, sensors/ISP suspended. Reload, route-resume and
zero-player units inactive/dead/exit0. No kernel C/build/reboot or package change.
Automatic lock/DPMS/suspend remainOFF per user preference; no manual-lock bypass.

No human readiness reply yet, so no audible tone played. Acoustic output,
mic/headphones, OEM DSP parity, long freeze/failed-reset DMA safety, S5 and complete
image/rootfs qualification remain open. This is not full audio/task acceptance.

## Host oracle integrity

The existing real-ALSA synthetic-control harness used Python assert for compiler,
layout, sequence and wrong-channel oracles. Those checks disappear under Python-O;
an optimized success alone was not proof they executed. This change replaces
those optional assertions with explicit failing requirements while keeping the
same real libasound fixtures, profiles and expected sequences. Normal parser
results remain evidence; historical optimized-only claims are not strengthened
retroactively. New normal/optimized tests include forced compiler and wrong-channel
negative cases. This is test-harness hardening, not new audio-driver DSP support.

Validation reproduced the old optimized wrong-channel false positive. New explicit checks reject that same malformed route and a deliberately failing compiler in both normal/-O modes; both ALSA1.2.16.1 and1.2.15.3 complete8layouts in both modes (32positive/negative layout scenarios). Profile files and pinned package inputs remain byte-identical; no package-release bump or automatic service hook.
