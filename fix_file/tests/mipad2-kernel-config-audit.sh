#!/bin/sh
# Validate the final, resolved kernel config used for a Mi Pad 2 build.
set -eu

config=${1:-.config}
[ -r "$config" ] || { echo "Config not readable: $config" >&2; exit 2; }

fail=0
need() {
	if grep -Eq "^$1$" "$config"; then
		printf 'OK   %s\n' "$1"
	else
		printf 'MISS %s\n' "$1" >&2
		fail=1
	fi
}

# Boot, storage and on-device diagnostics.
need 'CONFIG_EFI=y'
need 'CONFIG_EFI_MIXED=y'
need 'CONFIG_ACPI=y'
need 'CONFIG_MMC=y'
need 'CONFIG_MMC_SDHCI=y'
need 'CONFIG_MMC_SDHCI_ACPI=y'
need 'CONFIG_VFAT_FS=y'
need 'CONFIG_NLS_CODEPAGE_437=y'
need 'CONFIG_NLS_ASCII=y'
need 'CONFIG_IKCONFIG=y'
need 'CONFIG_IKCONFIG_PROC=y'
need 'CONFIG_CPU_FREQ=y'
need 'CONFIG_CPU_FREQ_DEFAULT_GOV_SCHEDUTIL=y'
need 'CONFIG_X86_INTEL_PSTATE=y'
need 'CONFIG_INTEL_IDLE=y'

# Display, input, GPIO, LEDs and sensors.
need 'CONFIG_DRM_I915=y'
need 'CONFIG_BACKLIGHT_LP855X=y'
need 'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y'
need 'CONFIG_PINCTRL_CHERRYVIEW=y'
need 'CONFIG_I2C_DESIGNWARE_CORE=y'
need 'CONFIG_I2C_HID_ACPI=y'
need 'CONFIG_I2C_HID_OF=y'
need 'CONFIG_HID_MULTITOUCH=y'
need 'CONFIG_INPUT_SOC_BUTTON_ARRAY=y'
need 'CONFIG_LEDS_KTD202X=y'
need 'CONFIG_LEDS_TRIGGER_INPUT_EVENTS=y'
need 'CONFIG_X86_ANDROID_TABLETS=y'
need 'CONFIG_HID_SENSOR_HUB=y'
need 'CONFIG_HID_SENSOR_ACCEL_3D=y'
need 'CONFIG_HID_SENSOR_GYRO_3D=y'
need 'CONFIG_HID_SENSOR_ALS=y'
need 'CONFIG_HID_SENSOR_MAGNETOMETER_3D=y'
need 'CONFIG_HID_SENSOR_INCLINOMETER_3D=y'
need 'CONFIG_HID_SENSOR_DEVICE_ROTATION=y'

# Power/charging and thermal management. Windows backup includes Intel DPTF
# thermal/power participant drivers; retain the corresponding Linux stack.
need 'CONFIG_BATTERY_BQ27XXX=y'
need 'CONFIG_CHARGER_BQ25890=y'
need 'CONFIG_INTEL_SOC_PMIC=y'
need 'CONFIG_INTEL_SOC_PMIC_CHTWC=y'
need 'CONFIG_SENSORS_CORETEMP=y'
need 'CONFIG_THERMAL=y'
need 'CONFIG_ACPI_THERMAL=y'
need 'CONFIG_ACPI_DPTF=y'
need 'CONFIG_DPTF_POWER=y'
need 'CONFIG_INT340X_THERMAL=y'
need 'CONFIG_INT3406_THERMAL=y'
need 'CONFIG_INTEL_SOC_DTS_THERMAL=y'
need 'CONFIG_X86_PKG_TEMP_THERMAL=y'
need 'CONFIG_INTEL_HFI_THERMAL=y'
need 'CONFIG_RTC_CLASS=y'
need 'CONFIG_PWM_LPSS_PLATFORM=y'

# Wi-Fi and Bluetooth must be built together with this exact kernel.
need 'CONFIG_CFG80211=m'
need 'CONFIG_BRCMFMAC=m'
need 'CONFIG_BRCMFMAC_PCIE=y'
need 'CONFIG_BT_HCIUART=m'
need 'CONFIG_BT_HCIUART_BCM=y'
need 'CONFIG_BT_BCM=m'
need 'CONFIG_SERIAL_DEV_BUS=y'

# Audio and both camera pipelines.
need 'CONFIG_SND_SST_ATOM_HIFI2_PLATFORM_ACPI=m'
need 'CONFIG_SND_SOC_INTEL_CHT_BSW_RT5659_MACH=m'
need 'CONFIG_SND_SOC_TFA989X=y'
need 'CONFIG_VIDEO_OV5693=m'
need 'CONFIG_VIDEO_T4KA3=m'
need 'CONFIG_VIDEO_DW9719=m'
need 'CONFIG_VIDEO_ATOMISP=m'

# USB host, Type-C role support and serial recovery gadget.
need 'CONFIG_USB_XHCI_HCD=y'
need 'CONFIG_USB_DWC3=y'
need 'CONFIG_USB_DWC3_DUAL_ROLE=y'
need 'CONFIG_USB_DWC3_PCI=y'
need 'CONFIG_USB_CONFIGFS=y'
need 'CONFIG_USB_CONFIGFS_SERIAL=y'
need 'CONFIG_USB_CONFIGFS_ACM=y'
need 'CONFIG_U_SERIAL_CONSOLE=y'
need 'CONFIG_EXTCON_INTEL_INT3496=y'
need 'CONFIG_EXTCON_INTEL_CHT_WC=y'

exit "$fail"
