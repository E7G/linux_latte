# Mi Pad 2 hardware support matrix

This page separates **code/configuration presence** from **runtime validation**. It is intentionally conservative: a driver being enabled in `xiaomipad2_defconfig` does not by itself prove that every hardware path is stable after boot, suspend/resume or repeated use.

## Status meanings

- **Integrated** — the current kernel tree/config contains the required Mi Pad 2 support path.
- **Runtime-checked** — `fix_file/tests/mipad2-hardware-smoke.sh` contains a current check for the expected runtime object/node.
- **Userspace required** — matching firmware or configuration from `fix_file/` is still needed.
- **Experimental** — implementation exists, but the project still expects real-hardware regressions or application compatibility problems.

## Matrix

| Hardware / function | Kernel/config status | Runtime/project check | Current notes |
| --- | --- | --- | --- |
| EFI x86_64 boot | Integrated | Boot itself | Device target is x86_64 Cherry Trail; `xiaomipad2_defconfig` is the project configuration. |
| Intel i915 display/GPU | Integrated | Runtime-checked | Smoke test expects both a DRM card and `/sys/class/drm/renderD128`. |
| LCD backlight | Integrated | Runtime-checked | Smoke test discovers a usable `/sys/class/backlight/*` device. |
| FTSC1000 touchscreen | Integrated | Runtime-checked | Smoke test recognizes `FTSC1000:00`; device numbering is discovered dynamically. |
| Bottom capacitive keys | Integrated | Indirect | Mi Pad 2-specific HID handling exists in `drivers/hid/hid-multitouch.c`; the old udev hwdb mapping is only a fallback for old builds/userspace. |
| BCM4356 Wi-Fi | Integrated as modules | Runtime-checked + userspace required | `cfg80211` / `brcmfmac` are modular. Device NVRAM is kept in `fix_file/`. |
| BCM4356 Bluetooth | Integrated as modules | Runtime-checked + userspace required | Broadcom HCI UART support is modular. `BCM4356A2.hcd` is kept in `fix_file/`. |
| RT5659 audio | Integrated | Runtime-checked + userspace required | ALSA card presence is checked; intended routing is supplied by `mipad2-alsa-ucm`. |
| Dual TFA9890 speaker path | Integrated/project profile | Functional audio test required | UCM profile contains the current userspace routing. Smoke test alone cannot prove stereo speaker output. |
| Headset / microphones | Integrated/project profile | Functional audio test required | Use `wpctl`, jack-state observation and recording tests from `fix_file/audio.md`. |
| DWC3 USB host/device dual-role | Integrated | Runtime-checked | Defconfig enables DWC3 PCI dual-role. Smoke test expects an actual UDC for gadget mode. |
| CDC ACM USB serial | Integrated + helper package | Optional runtime check | `mipad2-usb-serial` configures `/dev/ttyGS0`; gadget serial console support is enabled in the kernel. |
| Battery | Integrated target | Runtime-checked | Smoke test discovers a power-supply device with type `Battery`. |
| BQ25890 charging path | Integrated target | Runtime-checked | Smoke test expects a `USB` or `Mains` charger power-supply node. |
| Ambient light sensor | Integrated target | Runtime-checked | Smoke test expects IIO name `als`. |
| Accelerometer | Integrated target | Runtime-checked | Smoke test expects IIO name `accel_3d`. |
| Gyroscope | Integrated target | Runtime-checked | Smoke test expects IIO name `gyro_3d`. |
| Magnetometer | Integrated target | Runtime-checked | Smoke test expects IIO name `magn_3d`. |
| Inclination / orientation IIO | Integrated target | Runtime-checked | Smoke test expects `incli_3d` and `dev_rotation`. |
| Indicator LED | Integrated target | Runtime-checked | Smoke test expects `mipad2:rgb:indicator`. |
| Touch-button backlight LED | Integrated target | Runtime-checked | Smoke test expects `mipad2:white:touch-buttons-backlight`. |
| OV5693 front camera | Integrated as module | **Experimental** | Enumerates through AtomISP; use the supplied camera test script for actual streaming. |
| T4KA3 rear camera | Integrated as module | **Experimental** | Driver is in the kernel tree and has recent frame-interval/platform fixes. |
| DW9761 autofocus | Integrated through `dw9719` compatibility | **Experimental** | Smoke test searches for DW9761/DW9719 and `V4L2_CID_FOCUS_ABSOLUTE`. |
| AtomISP 2401 | Integrated as module | **Experimental**, CI compile-checked | Requires `shisp_2401a0_v21.bin`; current preferred firmware request is `intel/ipu/shisp_2401a0_v21.bin`. |
| VA-API video decode | Userspace feature | Project hardware-verified userspace setup | Current notes record `libva 2.24.0` + Intel i965 2.4.5 on CherryView; this is not a special kernel driver in this tree. |
| Suspend / resume | Kernel PM present | **Needs repeated regression** | Re-test wireless, audio, IIO, camera and USB after resume. |

## What CI actually proves

`.github/workflows/mipad2-camera-check.yml` currently validates important Mi Pad 2 configuration and source assumptions, including:

- camera module config for AtomISP, OV5693, T4KA3 and DW9719;
- Mi Pad 2 T4KA3 bridge/platform definitions;
- the 1280×720 AtomISP fallback-format change;
- recent AtomISP frame-interval/allocation code paths;
- Mi Pad 2 capacitive-key HID hooks;
- DWC3 dual-role and USB gadget serial config;
- modular BCM4356 Wi-Fi/Bluetooth config;
- syntax/basic integration of recovery, USB serial and hardware smoke scripts.

It also compiles selected camera/HID objects. This is a useful regression guard, but **it is not equivalent to a full real-device hardware test and should not be described as such**.

## Recommended real-device regression sequence

After installing a new kernel:

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

Then exercise the subsystems that a node-existence test cannot fully validate, especially audio, suspend/resume and cameras.

For cameras:

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

After suspend/resume, repeat the smoke test and any subsystem-specific test relevant to the change being evaluated.

## Source of truth

When this document and the code disagree, the current `main` branch is the source of truth. In particular check:

- `arch/x86/configs/xiaomipad2_defconfig` for build-time feature selection;
- `.github/workflows/mipad2-camera-check.yml` for CI-enforced assumptions;
- `fix_file/tests/mipad2-hardware-smoke.sh` for expected runtime nodes;
- `fix_file/packages/README.md` for userspace helper-package status;
- `KNOWN_ISSUES.md` for limitations that should not be presented as fully solved.
