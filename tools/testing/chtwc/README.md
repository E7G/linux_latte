# CHT Whiskey Cove ADC integration

This is one component of the complete Mi Pad2 thermal stack, not an OEM-equivalent
heat fix. The Kconfig option defaults off. Dedicated CI builds a separate7.2 ADC
integration image with this driver as a module; it does not deploy it. The daily3
configuration and default verifier release gate remain unchanged. Explicit adc1
flavor additionally requires the ADC module and verifies every module signature.

## Provenance and interface

Register/channel groups come from Intel's GPLv2 Android implementation at
[Xiaomi Mi Pad2 MFD source](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/mfd/intel_soc_pmic_wc.c).
The first11 register/request/completion triples match that table. VREF aliases
AGND without explaining a mux; it is not exposed as a fabricated independent
reading. VBAT follows the MFD label although the vendor enum calls it VBUS.

IIO retains existing raw12-bit counts and labels. Resistance aliases additionally
expose nominal ohms via in_resistanceN_input for BATID, BATTEMP0/1, SYSTEMP0/1/2
and USBID. Both count and current-source selector come from ONE completed
transaction under the acquisition/PM mutex; no scale read from a second sample.
The factor/1000 matches the vendor OpRegion and ALERT-ohm representation, not
the legacy IIO factor/10000 ten-ohm-unit output. This does not calibrate the board,
enable thermal policy or publish voltages. Board temperatures require the optional factory LPAT path below.
The PMIC die is not decoded with the thermistor transfer function.
Reserved thermistor source codes return ENODATA. Voltage and PMIC die calibration remain incomplete.

## Ownership and lifecycle

- One sleepable mutex serializes acquisition with suspend/remove.
- Only the MFD-domain ADC virtual IRQ is enabled for a transaction. MIRQLVL1
  belongs to parent regmap-IRQ; GPIO/thermal/BCU/charger IRQs are untouched.
- W1C completion status is written only with this transaction's group bit.
  Other pending groups and the monitor-tick bit are not acknowledged.
- Conversion mask bits0–6 are owned. Probe refuses an unmasked unsupported
  monitor tick; bit7 is preserved.
- Probe claims the exclusive ADC virq before changing masks. If that claim
  fails, neither quiesce nor restoration writes a saved preimage over an owner.
- Handler completion is drained before reuse/publication/restoring masks.
  Saved owned-mask bits are restored after free_irq.
- Timeout, uncertain command write, failed completion/cleanup quarantine further
  acquisition until reprobe. Late completions cannot become subsequent samples.
- Sleep does not hold a task-owned mutex across callbacks. Hardware-idle waits
  are bounded; resume does not silently clear quarantine.
- Autonomous monitor periods, charger/BCU controls are not rewritten.
  No thermal OpRegion is registered/rebound.

Two equal high/low/high observations are a bounded stability check, not proof
of a hardware latch, absence of ABA changes or autonomous-monitor freshness.
Firmware/SMM ownership still requires independent verification.

## Tests and remaining gates

Run python3 tools/testing/chtwc/run-tests.py. The same header used by the driver
is tested under O2 and ASan/UBSan: all status/group combinations, each operation's
bus failure (including writes that reached hardware), partial arm, busy/timeout,
cleanup failure, reserved selectors, unstable/stabilizing samples and no output
publication on error. These do not execute kernel IRQ scheduling, PM or devres.
Full kernel/module compilation/linking is a separate mandatory gate.

Before hardware load, inspect build results and preserve rollback/serial capture.
Validate raw freshness/IRQ counts, unload/reload and sleep/wake independently.
Do not enable a temperature-policy daemon from raw ADC counts, fake AVBG/AVBD,
or bypass virtual-GPIO/thermal-IRQ/die/LPAT integration gates.
Upstream PRs remain paused; this work is for the user's own integrated branch.


## PMIC OpRegion registration reentry

`python3 tools/testing/chtwc/test-pmic-init.py --cc gcc` extracts the exact
current `intel_pmic_install_opregion_handler()` body and context/data structures,
then compiles them with synchronous ACPI registration and allocation stubs.
The installed context must already contain the callback data, mutex, regmap and
optional LPAT when a connecting `_REG` reenters. Tests cover power/thermal table
combinations, absent/present LPAT, each registration failure and reverse unwind,
invalid arguments, allocation failure and publication only after full success.
GCC/Clang O2 and ASan/UBSan are separate runs. A negative control restores only
the previous late data assignment and must fail at the synchronous reentry.

This is a real-installer/mock-ACPI regression, not an AML interpreter or hardware
test. It does not demonstrate that Mi Pad2 firmware reentered on a previous boot,
establish a historical crash cause, enable thermal OpRegions or calibrate any
temperature. The separate `pmic1` full image retains the ADC module requirements;
its build and signature verification are not boot or heat-fix qualification.


## Mi Pad2 factory LPAT board temperatures

The optional constant `LPAT` package on the parent PMIC converts nominal ohms
from SYSTEMP0/1/2 to decikelvin. In the factory DPTF SSDT, the `_TMP` methods
of STR0/1/2 reference PMI5.TMP0/1/2 respectively. STR3 uses TMP3 and needs
separate qualification. Firmware did not expose STR1 as a thermal zone during
the 2026-11-19 test. In the LPAT table, 47000 ohms maps to 2981 decikelvin.
This is the PMIC table, NOT INT340x's centi-Celsius LPAT convention. IIO processed
temperature is milli-Celsius, using the kernel's -273150 absolute-zero offset.
Thus the factory 2981 marker is 24950 mC, not silently rounded to 25000 mC.

Only the Mi Pad2 MFD model is supported. The loader accepts a constant package,
not a method, validates integer widths before narrowing, strictly ascending
temperature/descending positive resistance, count bounds and duplicate points.
No available/valid table means unchanged raw and ohm paths, no processed TEMP
attributes. Allocation failure remains a probe error. The channel array is per
device and only in_temp5/6/7_input are added; battery, ID and PMIC die get no
invented temperature. Current and count come from one completed acquisition
under the existing PM/transaction lock. Rail codes and invalid selectors return
ENODATA; readings outside the table return ERANGE without extrapolation or
publishing a partial result. Signed 64-bit interpolation retains milli-Celsius
precision. Negative Celsius is a result, never confused with an errno.

`test-lpat.py --cc gcc` (also clang) compiles the actual conversion header and
extracts the real loader/read_raw bodies into mock ACPI/IRQ contexts, O2 and
ASan/UBSan separately. It tests all 4097 counts/16 selectors on all three board
channels against an independent weighted-endpoint oracle; malformed/method/
wide/duplicate tables, allocation failures, arithmetic extremes, forbidden
channels, PM/removal/fault and acquisition failures, single acquisition and
unchanged raw/ohm output. Removing the constant-package guard must fail the
method-evaluation negative control. Source ABI gates are not kernel execution.

Reference: latte-dev/android_kernel_xiaomi_latte d2afb1de9a761ff01dafdf9efe4736e521ab71f6,
vendor `wc_opregion.c` resistance/ALERT ABI (factor/1000), not legacy IIO's
factor/10000 ten-ohm representation. Test fixture records the 30-point factory
PMI5 table from DSDT SHA256 fe557b8b9d4b71a0d9cd443cf8a6d95e42ff6d9fb155bb1c15e9e12a78a70536.
No raw device logs, private ACPI dumps or identifying traces are included.

The full `lpat1` image has its own release and signed-module artifact gates.
Build, hardware temperature freshness/IRQ and sleep/wake are independent gates.
This adds factory-derived readings, not independently calibrated thermometry.
It registers no thermal zones, evaluates no `_TMP`, forces no AVBG/AVBD gates,
rewrites no monitor/thermal/GPIO/charger controls and enables no thermal policy.
The missing virtual-GPIO/thermal-IRQ/autonomous-monitor policy remains separate;
this alone is not proof of a heat or freeze fix.
