# Mi Pad 2 runtime support files

`fix_file/` contains the firmware, userspace configuration, local Arch packages and hardware regression helpers used together with the current `xiaomipad2_defconfig` kernel.

These files are not all kernel patches. Some hardware support requires both the kernel driver and the matching firmware/userspace configuration.

## Firmware

### Wi-Fi — BCM4356

The default kernel configuration builds `cfg80211` and `brcmfmac` as modules. Install the Mi Pad 2 board data as:

```bash
sudo install -Dm644 \
  "fix_file/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt" \
  "/usr/lib/firmware/brcm/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt"
```

Most distributions make `/lib/firmware` point at `/usr/lib/firmware`; use the firmware directory used by your distribution.

If `dmesg` shows that `brcmfmac` requests the generic `brcmfmac4356-pcie.txt` name instead of the DMI-specific file, copy the same board data to that requested name. Prefer following the filename printed by the driver rather than renaming files blindly.

Useful checks:

```bash
sudo modprobe brcmfmac
dmesg | grep -i brcm
ip link
```

### Bluetooth — BCM4356A2

The current defconfig builds Broadcom Bluetooth/HCI UART support as modules. Install the controller patch firmware as:

```bash
sudo install -Dm644 fix_file/BCM4356A2.hcd \
  /usr/lib/firmware/brcm/BCM4356A2.hcd
```

Then check the kernel log and HCI device rather than assuming firmware load succeeded:

```bash
dmesg | grep -Ei 'bluetooth|btbcm|hci'
bluetoothctl list
```

### Intel AtomISP camera firmware

Prefer installing [`mipad2-camera-support`](./packages/mipad2-camera-support/), because it installs both the module-load list and the firmware at the path expected by the current package:

```bash
cd fix_file/packages/mipad2-camera-support
makepkg -si
```

The firmware path is:

```text
/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin
```

For a manual install:

```bash
sudo install -Dm644 fix_file/shisp_2401a0_v21.bin \
  /usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin
```

The old instruction that placed this file directly in `/lib/firmware/` is no longer the preferred layout.

## Local packages

Each directory under `fix_file/packages/` is a small local Arch package. Run `makepkg` **inside the package directory**.

| Package | Purpose |
| --- | --- |
| `mipad2-alsa-ucm` | UCM profiles for RT5659 audio under PipeWire/WirePlumber |
| `mipad2-camera-support` | AtomISP firmware and camera module-load configuration |
| `mipad2-recovery` | Timeshift/Btrfs backup and one-command recovery helpers |
| `mipad2-test-no-idle` | opt-in GNOME test mode that inhibits idle blanking/suspend |
| `mipad2-usb-gadget` | configfs ECM/RNDIS USB Ethernet gadget |
| `mipad2-usb-serial` | configfs CDC ACM serial console/debug path |

Example:

```bash
cd fix_file/packages/mipad2-alsa-ucm
makepkg -si
```

Audio-specific notes are in [`audio.md`](./audio.md). USB device-mode setup is in [`USB_OTG_Gadget.md`](./USB_OTG_Gadget.md).

## Cameras

The current tree integrates the camera-side kernel work instead of requiring `latte-camera-t4ka3.patch` to be applied manually:

- OV5693 front camera uses the in-tree sensor driver.
- T4KA3 rear camera driver is integrated in the kernel tree and enabled as a module by `xiaomipad2_defconfig`.
- The rear DW9761 VCM is handled through the compatible `dw9719` driver path.
- AtomISP includes Mi Pad 2 graph/default-format fixes used by the supplied tests.
- `fix_file/latte-camera-t4ka3.patch` is retained as a reference/backport artifact; do not apply it again to this tree.

Basic inspection:

```bash
sudo modprobe atomisp
sudo modprobe ov5693
sudo modprobe t4ka3
sudo modprobe dw9719
dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97'
media-ctl -p
v4l2-ctl --list-devices
```

Camera support is still regression-sensitive. A successful CI compile is not proof of successful capture on real hardware; use the scripts under [`tests/`](./tests/).

## Touchscreen navigation buttons

The current kernel contains a Mi Pad 2 specific mapping in `hid-multitouch` for the FTSC1000 navigation-button keyboard interface (VID:PID `2808:509c`):

- Menu chord → `KEY_MENU`
- center/Home key → `KEY_HOME`
- Back key → `KEY_BACK`

Therefore the old custom `60-keyboard.hwdb` workaround is **not required when running this kernel**. Keep a userspace hwdb override only if you intentionally use a different/upstream kernel without the Mi Pad 2 HID mapping.

## Video decode acceleration

Mi Pad 2 has been used successfully with `libva 2.24.0` and `Intel i965 driver 2.4.5`; there is no need to force a downgrade to `libva 2.21.0-1` solely for this kernel.

```bash
vainfo
```

A working userspace setup should report the Intel CherryView i965 driver and the supported decode profiles. If a distribution defaults to an incompatible VA-API driver, prefer its `libva-intel-driver`/i965 package. This is a userspace driver choice, not a reason to patch the kernel.

## Hardware regression tests

See [`tests/README.md`](./tests/README.md). The smoke test now covers substantially more than camera nodes: Wi-Fi, Bluetooth, ALSA, backlight, touchscreen identification, i915 render nodes, LEDs, USB serial state, battery/charger, IIO sensors, UDC, camera nodes and VCM state are among its checks.

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```
