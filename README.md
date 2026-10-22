# Linux for Xiaomi Mi Pad 2 (latte)

This branch contains an in-progress Linux 7.2.0 kernel integration for the x86_64 Xiaomi Mi Pad 2 (latte), together with device-specific fixes, firmware helpers, userspace integration packages and hardware regression scripts.

Current 7.2 candidate: requested upstream `9928c7b8d00c` plus the retained
6.14 integration history. All 39 merge conflicts are resolved; focused compilation
and 32 host regressions pass. Full bzImage/modules build also passes;
hardware qualification remains open.
The installed tablet and stable GRUB default have not been switched.
See [7.2 migration status](fix_file/tests/mipad2-7.2-integration.md).
UCM pkgrel8 now preserves 6.14 rollback by detecting complete amplifier control
pairs; real ALSA parser/sequence tests pass on two library versions, not hardware.
The detailed 6.14 evidence below is historical and is not 7.2 hardware validation.

The device defconfig is `arch/x86/configs/xiaomipad2_defconfig`. The `cachyos-mipad2` branch uses the local version suffix `-mipad2-cachyos`.

For the Mi Pad 2 system, `E7G/linux_latte:cachyos-mipad2` is the device-kernel branch and `E7G/xiaomi-latte-flash_tools:arch_linux` is the image-build branch; the image builder pins the resolved kernel commit. `main` can diverge and is not an automatic source of truth for the installed tablet kernel.

The in-progress 6.14 integration is published as `codex/mipad2-6.14-integrated`. Previous scoped hardware run was r15 built source `616abdb8f`: standard V4L2 buffer fields and explicit legacy/typed metadata layouts pass BOTH-sensor1440-frame long gates; five idle crop extremes are fixed. Original3876frames/warm96 and14+21 explicit30fps matrices pass. Startingrear streaming compliance now83/83(warnings2), but **front-start compliance still times out and five frontend default-rate formats still do not stream**. The earlier shortmetadata run failed cadence and remains retained; longsuccess doesn't explain that drift. Read [r15 scoped evidence and retained failures](fix_file/tests/mipad2-6.14-r15-validation.md). Full interval/3A/AWB/GUI/otherhardware andflash-toolsintegration remain open. Electrical audio/S0I3 passed, acousticconfirmation deferred. Stable saved default remains `mipad2-bqdiag1`, candidates one-shot only. R16 built source `214a29ba2` is now one-shot booted: BOTH-sensor26 default no-S_PARM cases(6240frames) and13 front minimum cases(3120frames) pass; both-start unmodified streaming compliance83/83 each now passes. Two known120fps modes are preserved. **Initial short metadata cadence still failed**, independent long metadata passes; no full3A/AWB/GUI/flash-image completion claimed. See [R16 scoped evidence](fix_file/tests/mipad2-6.14-r16-validation.md). R17 built source `9b3361d4b` is now one-shot tested:1440 guarded ACTIVE/TRY frames and both-sensor9360 default/min frames pass, but **direct sensor control events fail; rear GUI hot-switch S_FMT fails; final RTC has0us S0I3 despite waking**. Our restoration harness also omitted test-pattern controls; those were later disabled. Front GUI was user-confirmed normal, rear was user-confirmed recovered after an idle format reset; powered hot-format source fix remains pending. No full imagery/3A/recording/low-power completion claimed. [R17 scope and remaining transactions](fix_file/tests/mipad2-6.14-r17-validation.md). R18 built source `86c16f5c7` is one-shot tested: powered rear width/HBLANK coherence and both-sensor per-FD events pass; sensor46/46 and video83/83 each, guarded1440frames and default/min9360frames pass. User confirms both GUI cameras after repeated switching; three reopen processes deliver frames and clean shutdown passes. Final10s RTC adds9,409,088us S0I3. Own two failed test fixtures and their separate recovery/corrected results are retained. Full I2C/PM transactions, 3A/quality/recording, highrates, otherhardware and flash-image boot remain incomplete; no default replacement. [R18 verification scope](fix_file/tests/mipad2-6.14-r18-validation.md).

> This is a device enablement/development kernel, not a generic distribution or fully hardened kernel. The Mi Pad 2 defconfig enables the kernel CPU mitigation framework by default; performance comparisons may opt out with `mitigations=off` at boot. See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for remaining limitations.

## Current status

The table below describes what is present in the current source/configuration. “Available” does not necessarily mean every distribution/userspace combination has been fully validated on hardware.

| Area | Current state | Notes |
| --- | --- | --- |
| Display / GPU | Available | i915 DRM is expected; the hardware smoke test checks both the DRM card and render node. |
| LCD backlight | Available / regression-tested by script | The smoke test checks for a usable backlight device. |
| Touchscreen | Available | The smoke test recognizes the Mi Pad 2 `FTSC1000:00` input device. |
| Capacitive bezel keys | Integrated | Mi Pad 2-specific HID handling is in the kernel tree. The old udev hwdb mapping in `fix_file/README.md` is now only a fallback. |
| Wi-Fi | Available, firmware required | BCM4356 support is built as modules (`cfg80211` / `brcmfmac`). Device NVRAM is kept under `fix_file/`. |
| Bluetooth | Available, firmware required | Broadcom HCI UART support is modular. `BCM4356A2.hcd` is provided under `fix_file/`. |
| Audio | Speaker output confirmed on 6.14 | On 2026-10-05 the user heard the generic dual-TFA9890 path after restoring RT5659 hardware/cache coherence. The installed reset/rebind fix passed live rebind and RTC-resume clock/amp-ready checks. r4-r6 one-shot cold boots and 10 s s2idle recovery passed silent electrical checks without manual DAPM repair; the user heard r4-r6 short tones. Factory DSP and long-duration audio soak remain separate gates. Uses the `mipad2-alsa-ucm` profile. |
| USB host / device mode | Available | DWC3 PCI dual-role support is enabled. Gadget mode may still require the firmware/BIOS OTG setting described in `fix_file/USB_OTG_Gadget.md`. |
| USB serial debug | Available | `mipad2-usb-serial` exposes CDC ACM `/dev/ttyGS0`; with the current kernel config it can also act as a kernel console and replay the printk ring buffer after USB enumeration. |
| Battery / charger | Integrated and live-validated | BQ25890 uses the Xiaomi 4.400 V VREG / 256 mA termination profile; BQ27520 reports the 6190 mAh design capacity and the former Full@83% issue is resolved. |
| TXE / MEI | Integrated and live-validated | Intel Trusted Execution Engine 8086:2298 binds to `mei_txe` and exposes `/dev/mei0`. |
| IIO sensors | Standard orientation live-validated | ALS, accelerometer, gyro, magnetometer, inclination and device-rotation nodes enumerate. The Mi Pad 2 matrices and four physical display orientations were verified; proprietary Windows ISS sensor payloads remain unmapped. |
| Indicator / touch-key LEDs | Integrated, verify on device | The regression script checks `mipad2:rgb:indicator` and `mipad2:white:touch-buttons-backlight`. |
| Front camera | Experimental | OV5693 uses the in-tree driver through AtomISP. r7 restores default exposure after transient format probes. The unbooted r8 candidate adds accurate/adjustable frame periods for OV5693 and T4KA3, with standard G/S_PARM responses and legacy CI_MODE requests retained. Direct-capture 3A/white-balance tuning remains open. |
| Rear camera | Experimental | T4KA3 support is integrated in this kernel tree; DW9761 focus is handled through the compatible `dw9719` driver. |
| Video decode | Userspace-verified | `libva 2.24.0` with Intel i965 driver 2.4.5 has been verified on CherryView; see `fix_file/README.md`. |
| Suspend / resume | Baseline validated; keep regression testing | An 8 s s2idle test spent about 7.43 s in S0I3 (~93%); Wi-Fi/SSH, USB gadget, audio and camera recovered successfully. Re-run after power/ACPI/media changes. |

### Camera status

The AtomISP camera stack is still the least mature part of this port. The current tree includes:

- OV5693 front sensor support, including r7 exposure-default restoration across format probing;
- integrated T4KA3 rear sensor support;
- DW9761 VCM compatibility through `dw9719`;
- Mi Pad 2 AtomISP platform/bridge changes;
- a conservative 1280×720 default format for clients that allocate buffers before setting a format;
- frame-interval handling and recent AtomISP allocation fixes;
- firmware/userspace integration through `fix_file/packages/mipad2-camera-support`.

Camera support should therefore be treated as **testable but still under active development**, not as fully stable. The supplied camera test scripts may expose AtomISP hangs; if a test leaves the driver stuck in an uninterruptible state, reboot before continuing.

## Build

On Windows hosts, keep the kernel checkout on a case-sensitive Linux filesystem
(for example, inside WSL's Linux filesystem), not a case-insensitive NTFS path.
This source tree contains distinct case-only paths such as `xt_DSCP.c` and
`xt_dscp.c`; a case-insensitive checkout aliases them and can replace a target
driver with a different match driver without a reliable build failure.

The current Mi Pad 2 defconfig requests Clang ThinLTO (`CONFIG_LTO_CLANG_THIN=y`). For a reproducible build that preserves the intended configuration, LLVM/Clang is therefore the recommended toolchain and `LLVM=1` should be passed consistently:

```bash
make LLVM=1 xiaomipad2_defconfig
make -j"$(nproc)" LLVM=1
```

To build Debian binary packages:

```bash
make LLVM=1 xiaomipad2_defconfig
make -j"$(nproc)" LLVM=1 bindeb-pkg
```

`deb-pkg` can also be used when source-package output is wanted. If you intentionally build with a different toolchain, inspect the resulting `.config` because toolchain-dependent Kconfig options may be adjusted; do not assume the final configuration is identical to the checked-in defconfig.

## Runtime files and helper packages

Device-specific runtime material is under `fix_file/`:

- `fix_file/README.md` — firmware and userspace integration overview;
- `fix_file/audio.md` — RT5659/TFA9890 UCM setup;
- `fix_file/USB_OTG_Gadget.md` — USB device-mode requirements and serial-debug setup;
- [`fix_file/packages/README.md`](fix_file/packages/README.md) — which helper packages are current, optional or legacy;
- `fix_file/tests/README.md` — hardware smoke tests and AtomISP camera tests.

The old `fix_file/latte-camera-t4ka3.patch` is kept only as a reference/backport artifact. The T4KA3 implementation is already integrated into the current kernel tree and must not be applied again.

## Hardware regression checks

Run the read-mostly hardware smoke test after a cold boot and after suspend/resume:

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

It checks the currently expected runtime devices, including Wi-Fi, Bluetooth, ALSA, backlight, touch, i915 DRM, LEDs, power, IIO sensors, UDC and the camera topology. It does **not** actively stream the camera unless `MIPAD2_ACTIVE_CAMERA_TEST=1` is explicitly set.

For camera-specific testing:

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

See `fix_file/tests/README.md` before running repeated camera tests.

## Firmware notes

Some hardware still needs device-specific firmware/userspace files in addition to the kernel:

- Wi-Fi: `fix_file/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt` → the distribution's Broadcom firmware directory, normally `/usr/lib/firmware/brcm/` or `/lib/firmware/brcm/`;
- Bluetooth: `fix_file/BCM4356A2.hcd` → the same Broadcom firmware directory;
- AtomISP: the current driver first requests `intel/ipu/shisp_2401a0_v21.bin`. The recommended `mipad2-camera-support` package installs it as `/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin`.

For compatibility, the AtomISP driver falls back to the old top-level filename `shisp_2401a0_v21.bin` if the preferred `intel/ipu/` request fails. New installations should use the `intel/ipu/` layout rather than relying on that fallback.

`/usr/lib/firmware` and `/lib/firmware` may refer to the same location on merged-/usr distributions, but that is a userspace/distribution detail. Check `dmesg` for the exact filename requested by the kernel before renaming files blindly.

## Known limitations

The most important current limitations are tracked in [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md), including:

- experimental AtomISP behavior and possible camera hangs;
- suspend/resume regression requirements;
- UDC / firmware dependence for USB gadget mode;
- the conflict between the current USB serial package and the old USB Ethernet gadget package;
- firmware/NVRAM requirements for BCM4356;
- device-oriented rather than generic-distro hardening; the defconfig enables CPU mitigations by default, while `mitigations=off` is an explicit performance-only boot override.

## Reporting problems

For hardware regressions, include at least:

```bash
uname -a
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
dmesg | grep -Ei 'atomisp|t4ka3|ov5693|dw97|brcm|bluetooth|rt5659|bq25890|i915'
```

For camera problems also include:

```bash
media-ctl -p
v4l2-ctl --list-devices
```

Please describe whether the failure happens on cold boot, only after suspend/resume, or only after a camera/audio/USB device has already been used.

## Upstream Linux documentation

This remains a normal Linux kernel source tree. General kernel build and development documentation is under `Documentation/` and at https://docs.kernel.org/.

R19 source `8c57f2be2` is fully built and one-shot/hardware tested: [bounded results and remaining scope](fix_file/MIPAD2_R19_HARDWARE.md). No Android parity/default-promotion claim.
