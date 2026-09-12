# Linux for Xiaomi Mi Pad 2 (latte)

This repository contains a Linux 6.14 based kernel tree for the x86_64 Xiaomi Mi Pad 2 (latte), together with device-specific fixes, firmware helpers, userspace integration packages and hardware regression scripts.

The device defconfig is `arch/x86/configs/xiaomipad2_defconfig`. Current builds use the local version suffix `-mipad2-complete`.

> This is a device enablement/development kernel, not a generic distribution or hardened kernel. The current defconfig intentionally contains development-oriented options and currently has CPU mitigations disabled. Review the configuration before using it for security-sensitive workloads. See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for the current limitations.

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
| Audio | Available with userspace profile | RT5659 / dual TFA9890 support uses the `mipad2-alsa-ucm` profile. See `fix_file/audio.md`. |
| USB host / device mode | Available | DWC3 PCI dual-role support is enabled. Gadget mode may still require the firmware/BIOS OTG setting described in `fix_file/USB_OTG_Gadget.md`. |
| USB serial debug | Available | `mipad2-usb-serial` exposes CDC ACM `/dev/ttyGS0`; with the current kernel config it can also act as a kernel console and replay the printk ring buffer after USB enumeration. |
| Battery / charger | Integrated, verify on device | The regression script checks a battery power-supply node and the BQ25890 charger path. |
| IIO sensors | Integrated, verify on device | The regression script expects ALS, accelerometer, gyro, magnetometer, inclination and device-rotation IIO devices. |
| Indicator / touch-key LEDs | Integrated, verify on device | The regression script checks `mipad2:rgb:indicator` and `mipad2:white:touch-buttons-backlight`. |
| Front camera | Experimental | OV5693 uses the in-tree driver through AtomISP. |
| Rear camera | Experimental | T4KA3 support is integrated in this kernel tree; DW9761 focus is handled through the compatible `dw9719` driver. |
| Video decode | Userspace-verified | `libva 2.24.0` with Intel i965 driver 2.4.5 has been verified on CherryView; see `fix_file/README.md`. |
| Suspend / resume | Needs regression testing | Re-test cameras, audio, wireless and sensors after suspend/resume; do not assume all peripherals recover on every userspace stack. |

### Camera status

The AtomISP camera stack is still the least mature part of this port. The current tree includes:

- OV5693 front sensor support;
- integrated T4KA3 rear sensor support;
- DW9761 VCM compatibility through `dw9719`;
- Mi Pad 2 AtomISP platform/bridge changes;
- a conservative 1280×720 default format for clients that allocate buffers before setting a format;
- frame-interval handling and recent AtomISP allocation fixes;
- firmware/userspace integration through `fix_file/packages/mipad2-camera-support`.

Camera support should therefore be treated as **testable but still under active development**, not as fully stable. The supplied camera test scripts may expose AtomISP hangs; if a test leaves the driver stuck in an uninterruptible state, reboot before continuing.

## Build

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
- development-oriented defconfig choices such as disabled CPU mitigations.

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
