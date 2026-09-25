#!/bin/sh
# Guard the Xiaomi board-file that restores ACPI-hidden Mi Pad 2 I2C devices.
# These checks cover declarations only; runtime bus/device binding is separate.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

config=arch/x86/configs/xiaomipad2_defconfig
dmi=drivers/platform/x86/x86-android-tablets/dmi.c
board=drivers/platform/x86/x86-android-tablets/other.c

grep -q '^CONFIG_X86_ANDROID_TABLETS=y' "$config"
grep -Fq 'DMI_MATCH(DMI_SYS_VENDOR, "Xiaomi Inc")' "$dmi"
grep -Fq 'DMI_MATCH(DMI_PRODUCT_NAME, "Mipad2")' "$dmi"
grep -Fq 'driver_data = (void *)&xiaomi_mipad2_info' "$dmi"
if grep -Fq 'TXN27520:00' "$board"; then
	grep -Fq 'acpi_dev_hid_uid_match(adev, "TXN27520"' "$board"
	grep -Fq 'strscpy(client->name, "bq27520"' "$board"
else
	grep -Fq '.addr = 0x55' "$board"
	grep -Fq 'PCI0.I2C1' "$board"
	grep -Fq '.type = "bq27520"' "$board"
fi
grep -Fq '.type = "tfa9890"' "$board"
grep -Fq '.type = "ktd2026"' "$board"
grep -Fq 'PCI0.I2C2' "$board"
grep -Fq 'PCI0.I2C3' "$board"
grep -Fq '.addr = 0x34' "$board"
grep -Fq '.addr = 0x37' "$board"
grep -Fq '.addr = 0x30' "$board"

echo "PASS: Xiaomi DMI entry and hidden fuel-gauge, audio-amp, and LED I2C board declarations and the firmware-created fuel-gauge fixup exist."
echo "NOTE: this audit does not verify that firmware exposes the buses or devices bind at runtime."
