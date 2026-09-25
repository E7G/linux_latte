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
| Intel DPTF / platform thermal | Configured (ACPI_DPTF, DPTF_POWER, INT340X, Intel SoC DTS) | Diagnostic-only | Compare thermal zones, trips and cooling states at idle/load and after resume. Windows INF IDs are generic; real ACPI/runtime presence remains unverified. |
| Battery | Integrated target | Runtime-checked | Smoke test discovers a power-supply device with type `Battery`. |
| BQ25890 charging path | Integrated target | Runtime-checked | Smoke test expects a `USB` or `Mains` charger power-supply node. |
| Cherry Trail Whiskey Cove PMIC | INT34D3 Linux MFD/ACPI driver enabled | Compile-checked; runtime unverified | Windows PMIC INF lists generic Intel PMIC candidates including INT34D3; only live ACPI enumeration can identify the actual Mi Pad 2 variant. |
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

## Driver-reference and stability audit

A July 2026 [Debian report](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1142004) describes a full-platform i915 probe wedge on an unmodified Debian 6.12.95 kernel. The current branch already carries a Xiaomi PCI-subsystem-specific DPIO common B/C power-well quirk and initializes i915 quirks before display power-domain setup. CI now checks this device match, both guarded power-well paths, initialization order and compiles the affected objects. This static coverage is not proof of this branch's real-device display or suspend/resume behavior; those still need controlled Mi Pad 2 validation.

The [public Mi Pad 2 Windows 10 driver backup](https://github.com/brianwoo/mipad2-win10-howto) is useful for identifying device classes and candidate IDs, but its generic INF model lists are not a live Device Manager/ACPI dump and do not prove which compatible ID matched on a specific tablet. Do not copy proprietary Windows binaries into this kernel or infer a Linux register protocol from the driver name.

| Windows archive entry / ID evidence | Linux tree comparison | Remaining proof |
| --- | --- | --- |
| FocalTech touchscreen, FTSC1000 | Mi Pad 2 x86 Android-tablet support recognizes FTSC1000. | Confirm touch, orientation and suspend/resume on hardware. |
| LP8556 backlight, XMCC0001 | Kernel backlight driver has the Mi Pad 2 ACPI match. | Confirm brightness range and panel/backlight power sequencing after resume. |
| OV5693 (INT33BE) and T4KA3 (XMCC0003) | Corresponding Linux sensor drivers/AtomISP bridge entries exist. | Stream both cameras and test controls/focus on hardware. |
| Intel HID Event Filter (ACPI INT33D5) | Linux intel-hid contains the ACPI match; CONFIG_INTEL_HID_EVENT=y. | Confirm tablet hotkey events and wake behavior on-device. |
| Intel Serial IO I2C/UART (Windows INF lists ACPI 808622C1 / 8086228A) | Linux ACPI LPSS table matches both HIDs to Braswell I2C/UART descriptors; DesignWare I2C and UART are enabled in defconfig. | Verify that the tablet exposes these ACPI nodes, controllers enumerate and connected peripherals bind after boot/resume. |
| Intel HID Advanced Sensor Collection V2 (HID\VID_8086&PID_0002) / ISH | Linux enables CONFIG_INTEL_ISH_HID, CONFIG_HID_SENSOR_HUB and sensor-class drivers; CherryView ISH PCI ID is 8086:22D8. | Confirm the actual HID collection, IIO devices, sensor values/orientation and suspend/resume; the archive model list alone does not prove a live match. |
| BQMG0890 charger controller (XMCC0002) | No BQMG0890 Linux driver/ACPI match is present. Linux separately instantiates the TI BQ25890 charger and BQ27520 fuel gauge through the Cherry Trail Whiskey Cove path; this is not proof of parity with the OEM BQMG0890 interface. The archived BQMG0890 is a proprietary KMDF driver and imports ACPI OpRegion registration APIs, so its protocol cannot be safely inferred from the INF name. | Compare live ACPI devices and power-supply readings, then verify charge detection/current and battery reporting on-device. Treat exact BQMG0890 behavior as unresolved. |
| Realtek I2S codec INF lists INTCCFFD and 10EC5640 among its compatible IDs | Linux target configures the RT5659 path. The backup's broad INF model list does not identify which ID matched on this tablet. | Capture the tablet's actual ACPI codec ID and ALSA/I2C binding before claiming cross-OS codec equivalence. |

The Linux battery/charger mapping is also documented in [the upstream x86 Android-tablet device table](https://android.googlesource.com/kernel/common/%2B/e445c8b2aa2df0e49f6037886c32d54a5e3960b1/drivers/platform/x86/x86-android-tablets.c) and [the Cherry Trail Whiskey Cove I2C driver](https://android.googlesource.com/kernel/common/%2B/28174b15b2df1f47c005ec71ee5427e4ac8f46f0/drivers/i2c/busses/i2c-cht-wc.c). These establish the Linux BQ27520/BQ25890 path, not equivalence to the separate Windows BQMG0890 driver.



## Live Mi Pad 2 audit snapshot (2026-09-25)

A read-only SSH audit of the installed CachyOS kernel (`6.14.0-mipad2-cachyos-navkeys`) confirmed runtime enumeration, not full functional validation:

- FTSC1000 touch input appears under a generic `hid-over-i2c 2808:509C` event name; its `phys` field is `i2c-FTSC1000`. The smoke test matches that physical path. Touch interaction/orientation/resume are still untested.
- BCM4356A2 Bluetooth HCI and firmware enumerate, but `rfkill` reported Bluetooth soft-blocked (not hard-blocked); pairing and radio operation remain untested. The audit did not change this user/device state.
- The `INT34D3:00` Whiskey Cove PMIC is bound to `intel_soc_pmic_chtwc`; `i2c-14` is the BQ25890 charger adapter, with BQ25890 and BQ27520 clients bound to their Linux drivers. Battery was reported at 83%, 4.165 V. This does not establish parity with the OEM Windows BQMG0890 driver or validate charging under load.
- Thermal/DPTF zones and cooling devices enumerate. No load, trip-point, suspend/resume or throttling test was performed.
- The refreshed thermal audit identified acpitz=0 mC as suspicious and STR0/STR2/STR3 -273150 mC values as unavailable sentinels; other live readings included SoC DTS at 39-40 C, charger at 38 C, battery at 28.3 C and PNIT at 36 C. Cooling states were idle. No load/thermal-trip test was attempted.
- Trip-point audit further found SoC DTS passive trip entries at 0 mC and STR-zone passive entries at -274000 mC; both now print explicit quality flags alongside trip types. Actual STR-zone critical/hot trips were 85.05/82.05 C. This runtime snapshot is not enough to certify active thermal protection; no load/trip test was run.
- The live thermal zones exposed no cdev cooling-device bindings. thermald is absent/inactive, /sys/class/powercap is empty, and intel_pstate is in passive mode. Since ACPI/SoC trip data include invalid/unconfigured values, do not enable a generic thermald policy without device-specific validation; this is an unresolved thermal-control gap, not proof that firmware hardware-throttling fails. Linux defines -274000 mC as THERMAL_TEMP_INVALID ([kernel header](https://github.com/torvalds/linux/blob/master/include/linux/thermal.h)); see [thermald's INT340X support/prerequisites](https://github.com/intel/thermal_daemon).
- The full hardware smoke now runs the read-only thermal audit alongside zone enumeration so invalid samples/trips are visible in the default report.
- After integrating the rfkill helper, the full read-only hardware smoke script completed on the live CachyOS kernel with all required device-node checks passing; it explicitly reported Bluetooth soft-blocked. This was enumeration-only, not functional exercise.
- Read-only media queries confirmed v4l2-ctl --list-inputs lists both OV5693 (front) and T4KA3 (rear), with an AtomISP media graph. T4KA3 exposes its controls and 321468000 Hz link-frequency value. These metadata/input-enumeration results do not prove capture; rear CSI link is not enabled in the idle graph and camera streaming remains untested.
- No real audio playback/capture, touch gesture, camera streaming, BT pairing, or suspend/resume test was performed. These remain explicit gaps; node enumeration alone is not a pass.

## What CI actually proves

`.github/workflows/mipad2-camera-check.yml` currently validates important Mi Pad 2 configuration and source assumptions, including:

- Mi Pad 2 i915 PCI-subsystem match, DPIO common B/C power-well guard and quirk-before-power-domain ordering, plus W=1 compilation of affected i915 objects;
- camera module config for AtomISP, OV5693, T4KA3 and DW9719;
- Mi Pad 2 T4KA3 bridge/platform definitions;
- the 1280×720 AtomISP fallback-format change;
- recent AtomISP frame-interval/allocation code paths;
- Mi Pad 2 capacitive-key HID hooks;
- DWC3 dual-role and USB gadget serial config;
- modular BCM4356 Wi-Fi/Bluetooth config;
- AtomISP sensor/VCM module load-order audit against Mi Pad 2 Android init requirements;
- DPTF/thermal/charger defconfig settings plus mock-backed thermal readout tests;
- Xiaomi DMI board-file mapping and declarations for ACPI-hidden BQ27520, dual TFA9890 and KTD2026 I2C devices;
- RT5659/TFA989x audio-driver W=1 compilation plus static checks tying UCM left/right selections to the two amplifier DAIs;
- syntax/basic integration of recovery, USB serial and hardware smoke scripts.

It also compiles selected camera/HID and RT5659/TFA989x audio objects, and statically cross-checks the stereo UCM route declarations. These are useful regression guards, but **they are not equivalent to full real-device hardware tests and should not be described as such**.

## Recommended real-device regression sequence

After installing a new kernel:

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
sudo sh fix_file/tests/mipad2-thermal-audit.sh
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
