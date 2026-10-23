# Mi Pad 2: requested Linux 7.2 integration candidate

## Scope and provenance

- Requested base: E7G/linux_latte@9928c7b8d00c500ee97903afa1cc76c1c36ab2bc.
- Integrated history: codex/mipad2-6.14-integrated@3fb5c05197364c84097404e72bcac95444354f7e.
- True three-way common base: e89ea264f5ca311c9dca9088d964b80ec40472b4.
- Branch: `codex/mipad2-7.2-integrated`. This is 7.2.0, not a silent upgrade to another stable release.
- All 39 conflicted files were reviewed; merge history is retained rather than squashed/rebased over the old integration.

## Important compatibility work

The maintained CachyOS 7.2 BORE patch replaces the old 6.14 scheduler coherently.
Source: <https://github.com/CachyOS/kernel-patches/blob/master/7.2/sched/0001-bore.patch>.
Pinned Git blob: `2d96314602c6fa5a123ea2a97cbfd7547d196bf3`;
patch SHA256: `61b9543e400d6fb38a68ee2276538ae14834bec75d7b06d3e1ac9977174ff619`.
CACHY, alternative HZ choices, O3 and the unprivileged-user-namespace policy switch
remain available. The new queue-owned elevator lifecycle and timer API are used
by ADIOS; init failure does not free its caller-owned elevator_queue.

The x86-64 Mi Pad 2 configuration uses explicit Silvermont/Airmont compiler tuning,
never the newer build host's `-march=native`. Stock 7.2 module ABI handling is kept.
The defconfig also enables the new AtomISP INT3472 dependency; otherwise olddefconfig
silently drops the ISP driver. Atomic headers are regenerated from the merged
7.2 generators, including their generated checksums.

The sensor format/exposure/crop/metadata fixes are retained. AtomISP follows the
7.2 sensor/csi_remote_source separation and shared stop helper while retaining
format preservation, frame-layout checks, final-frame stop handshake, original
sensor errno and fatal-on-reset/recreate failure semantics. Existing typed
metadata IOCTLs remain whitelisted. Physical failed-reset/DMA safety remains
unresolved; passing host teardown tests is not proof of hardware quiescence.

Audio follows the requested upstream three-stage topology, no_pcm amplifier
links and board codec_conf prefixes. The cold-boot IF2 DAC_REF DAPM late_probe
fix remains. RT5659/TFA989x use the new 7.2 ASoC pointer/opaque DAPM APIs.
**UCM pkgrel8 supports both kernel families**: it selects a complete prefixed
`Left Amp Input`/`Right Amp Input` pair or the complete 6.14 legacy pair. Partial
layouts fail before mixer writes. Real ALSA parser/ctl_ext tests pass on two
library versions; this is not a physical audio or DAPM qualification.

The touchscreen reset and codec reset/LDO mappings use 7.2 Cherryview GPIO
secondary software nodes instead of the removed lookup-table integration API.
The physical GPIO mapping is retained; new hardware validation is still needed.

## Validation at this checkpoint

- LLVM 21.1.8, x86_64, O3, ThinLTO, HZ300, BORE, Silvermont defconfig.
- Focused scheduler, fork/sysctl/elevator, both sensors/VCM, AtomISP and both audio-codec/board objects compiled.
- All 32 existing host regression scripts pass after their synthetic API scaffolds were ported; their fault/order oracles are retained.
- Actual sensor/crop/Sensor-ISP/CSI extraction passes 160,000 fault-return cases.
  A separate swallowed-sensor-error mutation is rejected by the oracle.
- BORE/CACHY/USER_NS-disabled core compile also passes. Its maintained BORE
  patch currently leaves a reweight_entity missing-prototype warning.
- UCM package source SHA256 checks pass.
- Full bzImage/modules build passes for `7.2.0-mipad2-integrated-r1` (31 modules). No new hardware boot is claimed.

See `mipad2-7.2-port-host-results.json` for machine-readable scalar results.
These tests use explicit mocks: they do not establish optical quality, audio
output, real firmware timing, S0I3 residency, battery life or Android parity.

## DDR mailbox continuation

The 7.2 continuation fixes the unchecked split DDR DVFS mailbox RMW and validates
power-on preconditions without abandoning an already submitted power-off ack.
See [DDR DVFS error-path evidence](mipad2-ddr-dvfs-validation.md). Its host
interleaving/error tests do not close the physical failed-reset/DMA or S0I3 gate.
The resulting kernel C change is a new **r2** candidate, not a relabelled r1.

## Deployment gate

The tablet, stable 6.14 kernel and saved GRUB default are unchanged. Do not replace
the stable entry with this candidate. First complete full link/module checks,
prepare the matching userspace profiles, preserve boot diagnostics and recovery,
then use an isolated one-shot entry for actual hardware qualification.

## R2 physical camera regression / r3 continuation

R2 booted, but actual default rear QBUF failed with zero frames. It is quarantined
and stable 6.14 restored. R3 fixes the V4L2 NULL callback/file-context boundary.
See [evidence and scope](mipad2-7.2-null-fh-validation.md); host tests are not
physical camera qualification. The requested upstream remains exact 9928c7b8.
