#!/bin/sh
set -eu

quirks=drivers/gpu/drm/i915/display/intel_quirks.c
quirks_h=drivers/gpu/drm/i915/display/intel_quirks.h
power=drivers/gpu/drm/i915/display/intel_display_power.c
driver=drivers/gpu/drm/i915/display/intel_display_driver.c

grep -Fq '{ 0x22b0, 0x1d72, 0x1502, quirk_no_vlv_disp_pw_dpio_cmn_bc_init }' "$quirks"
grep -Fq 'QUIRK_NO_VLV_DISP_PW_DPIO_CMN_BC_INIT' "$quirks_h"
test "$(grep -F -c 'intel_has_quirk(display, QUIRK_NO_VLV_DISP_PW_DPIO_CMN_BC_INIT)' "$power")" -eq 2
test "$(grep -F -c 'i915_power_well_instance(power_well)->id == VLV_DISP_PW_DPIO_CMN_BC' "$power")" -eq 2

awk '
/^int intel_display_driver_probe_noirq/ { in_probe = 1 }
in_probe && /intel_init_quirks\(display\);/ { quirks = NR }
in_probe && /intel_power_domains_init\(display\);/ { power = NR; exit }
END { if (!quirks || !power || quirks >= power) exit 1 }
' "$driver"

echo "PASS: Mi Pad 2 i915 quirk targets 8086:22b0/1d72:1502 and is initialized before display power domains."
