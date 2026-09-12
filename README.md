# linux_latte — Linux kernel for Xiaomi Mi Pad 2

`linux_latte` is a Linux kernel tree for the **Xiaomi Mi Pad 2 (latte)**, based on Linux **6.14** and carrying the device-specific work needed for the Intel Cherry Trail platform.

The project default configuration is `arch/x86/configs/xiaomipad2_defconfig`. It currently builds with the local version suffix `-mipad2-complete`.

> This is still a development kernel. Keep a known-good kernel/boot entry available, especially while testing camera, USB device mode, suspend/resume or other hardware changes.

The original upstream Linux kernel README is kept as [`README`](./README). This file documents the Mi Pad 2 specific state of this fork.

## Current state

The table below describes what is present in the **current code/configuration**. “Integrated” does not automatically mean every path has been verified on every device after every commit.

| Area | Current implementation | Notes |
| --- | --- | --- |
| Kernel | Linux 6.14 + `xiaomipad2_defconfig` | local version: `-mipad2-complete` |
| Wi-Fi | `brcmfmac` + `cfg80211` built as modules | BCM4356 board data/firmware is required; see `fix_file/` |
| Bluetooth | HCI UART + Broadcom support built as modules | BCM4356A2 firmware is provided under `fix_file/` |
| Audio | RT5659/ALSA kernel path + project UCM package | use `mipad2-alsa-ucm`; see [`fix_file/audio.md`](./fix_file/audio.md) |
| Display / GPU | upstream i915 path | hardware smoke test checks DRM card and render node |
| Touch / navigation keys | Mi Pad 2 FTSC1000 navigation-key mapping is handled in `hid-multitouch` | Menu/Home/Back no longer require the old hwdb workaround when using this kernel |
| Front camera | OV5693 + AtomISP | integrated, but camera runtime is still an experimental/regression-sensitive area |
| Rear camera | T4KA3 + DW9761-compatible VCM through `dw9719` + AtomISP | integrated; use the supplied camera support package and tests |
| USB host/device | DWC3 dual-role enabled | USB device/gadget mode also depends on firmware/BIOS configuration |
| USB Ethernet gadget | configfs ECM/RNDIS | `mipad2-usb-gadget` package |
| USB serial debug | configfs CDC ACM + `U_SERIAL_CONSOLE` | `mipad2-usb-serial` package; intended as a recovery/debug path |
| Battery / charger | included in hardware regression checks | verify on the target device with the smoke script |
| IIO sensors | ALS/accelerometer/gyro/magnetometer/orientation nodes are regression targets | verify on the target device with the smoke script |
| LEDs / backlight | included in hardware regression checks | verify on the target device with the smoke script |
| Video decode | userspace VA-API/i965 path | not a custom kernel decoder; see [`fix_file/README.md`](./fix_file/README.md) |

For the most useful real-device regression checks, see [`fix_file/tests/README.md`](./fix_file/tests/README.md).

## Build

The Mi Pad 2 defconfig enables ThinLTO, so a Clang/LLVM toolchain is the recommended full-build path.

```bash
make LLVM=1 xiaomipad2_defconfig
make LLVM=1 -j"$(nproc)"
```

The kernel image is produced at:

```text
arch/x86/boot/bzImage
```

Modules can be staged before installing them into a root filesystem:

```bash
rm -rf /tmp/mipad2-modules
make LLVM=1 modules_install INSTALL_MOD_PATH=/tmp/mipad2-modules
```

Do not overwrite your only bootable kernel while testing. Installation of `bzImage`, modules and initramfs is distribution/bootloader specific.

## Runtime support files

Device-specific firmware, userspace helpers, Arch-style local packages and regression scripts live under [`fix_file/`](./fix_file/README.md).

The currently maintained local packages are:

- `mipad2-alsa-ucm` — PipeWire/WirePlumber UCM profiles for Mi Pad 2 audio.
- `mipad2-camera-support` — AtomISP module-load list and `intel/ipu/shisp_2401a0_v21.bin` firmware.
- `mipad2-recovery` — Timeshift/Btrfs backup and recovery helpers.
- `mipad2-test-no-idle` — optional test mode that inhibits GNOME idle blanking/suspend.
- `mipad2-usb-gadget` — persistent configfs ECM/RNDIS USB networking.
- `mipad2-usb-serial` — CDC ACM USB serial console/debug path.

For Arch-based systems, build a local package by entering its directory first, for example:

```bash
cd fix_file/packages/mipad2-camera-support
makepkg -si
```

## Camera status

The current tree contains Mi Pad 2 specific AtomISP work, the rear T4KA3 sensor driver, OV5693 support, the DW9761-compatible VCM path via `dw9719`, and fixes for camera graph/default-format behaviour.

CI checks that the relevant drivers/configuration still compile, but **GitHub Actions cannot prove real camera capture on Mi Pad 2 hardware**. Treat camera support as experimental and run the supplied real-device tests after camera-related changes.

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

More detail is in [`fix_file/tests/README.md`](./fix_file/tests/README.md).

## USB device mode

The kernel enables DWC3 dual-role and configfs gadget functions used by the project. On Mi Pad 2, the firmware setting must expose USB OTG in **PCI Mode** before a usable UDC is expected under `/sys/class/udc`.

See [`fix_file/USB_OTG_Gadget.md`](./fix_file/USB_OTG_Gadget.md) before changing firmware variables. A wrong firmware setting can leave USB device mode unavailable.

`mipad2-usb-gadget` and `mipad2-usb-serial` are alternative configurations for the tablet's single UDC; do not enable both services at the same time.

## CI and testing

`.github/workflows/mipad2-camera-check.yml` currently performs configuration checks, compiles the camera/VCM/HID objects touched by this project, and syntax-checks the recovery/USB/test helper scripts.

That workflow is a **compile/static regression check**, not a replacement for Mi Pad 2 hardware testing.

The hardware smoke script checks the currently expected Wi-Fi, Bluetooth, ALSA, backlight, touchscreen identification, i915 DRM/render nodes, LEDs, USB serial state, camera/media nodes, battery, charger, IIO sensors, UDC, T4KA3 and VCM state. It is read-only unless the active camera test is explicitly enabled.

## Reporting regressions

When reporting a hardware regression, include at least the kernel commit, `uname -a`, the output of the smoke test and the relevant kernel log. For camera issues, also include the media graph and V4L2 device list:

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
media-ctl -p
v4l2-ctl --list-devices
dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97|brcm|rt5659|dwc3|bq25890'
```

Keeping reports tied to an exact commit is important because the camera and power-management paths are still being actively changed.
