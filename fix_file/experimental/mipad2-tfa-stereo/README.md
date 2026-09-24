# Mi Pad 2 experimental stereo speaker hotload

This is the **optional, out-of-tree** audio stack tested on Mi Pad 2 with
`6.14.0-mipad2-cachyos-navkeys`: two TFA9890 amplifiers, RT5659 codec and the
Cherry Trail machine driver. It is **not** included in initramfs or loaded at
boot. A failed hotload rolls back to the stock modules; do not install these
files over the stock kernel modules.

The TFA driver is based on [Xiaomi's latte Android kernel](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/latte-l-oss/sound/soc/codecs), with fixes for current ASoC APIs, DSP idle/restart and the right speaker's I2S slot. The RT5659 and machine sources derive from the corresponding Linux kernel drivers. See SPDX headers in each source file. The right amplifier's stereo selector is programmed as `0x804b` after DSP start; the left remains `0x800b`. Playback activity is signalled from RT5659 and the machine driver to keep both DSPs stable across idle transitions.

## Build

Requires a matching configured and built kernel source/output tree containing
`Module.symvers`, a C toolchain, `make`, `modinfo` and `sha256sum`.

```sh
./build.sh /path/to/linux-source /path/to/kernel-output
```

Output is `dist/<module-vermagic-release>/`. Build checks each module's
vermagic and writes `SHA256SUMS`. The build is for this specific kernel ABI;
do **not** load into another kernel release or an image with incompatible
symbol CRCs.

## Apply (manual, never at boot)

Copy the entire `dist/<release>/` directory to the tablet. The tablet must
already have its matching `tfa98xx.cnt` firmware, working UCM/PipeWire setup,
and the original `tfa989x`, `snd-soc-rt5659` and
`snd-soc-sst-cht-bsw-rt5659` modules available for rollback.

```sh
cd /path/to/copied/<release>
sha256sum -c SHA256SUMS
sudo ./hotload.sh status
sudo ./hotload.sh apply
sudo ./hotload.sh rollback  # manually restore the stock audio stack
```

By default, PipeWire runs as user `user`; set `MIPAD2_AUDIO_USER` if needed.
`apply` checks the live kernel release, waits for both factory DSPs to report
successful initialization, verifies DSP parking/recovery and rejects observed
`ret=-22` or timeout errors. It leaves the new modules resident only after
these tests pass. Rollback does not replace any on-disk system module.

An earlier hotload build was verified on the tablet with two low-volume
microphone-assisted left/right acoustic tests. The TFA and RT5659 modules
rebuilt here match the live modules' `srcversion`, but the rebuilt machine
driver currently does **not** match the live module's `srcversion` and has not
been reloaded on the tablet. Treat this package as buildable experimental
source, not as a fully reproduced live stack. The acoustic tests establish
distinct channel routing, not speaker frequency response, loudness calibration
or long-term reliability.

## Remaining validation

- Long playback/idle cycling, headphone and microphone use, suspend/resume.
- Human listening for distortion, phase, and speaker protection behavior.
- Repeat with every kernel rebuild; no automatic boot integration until those
  tests pass and rollback/recovery is demonstrated with someone at the device.
