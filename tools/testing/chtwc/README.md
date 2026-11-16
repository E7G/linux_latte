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

IIO exposes raw12-bit counts and labels, not degrees, ohms or millivolts.
The PMIC die is not decoded with the thermistor transfer function.
Reserved thermistor source codes return ENODATA. Physical scaling, LPAT units
and calibrated die conversion remain required for processed values.

## Ownership and lifecycle

- One sleepable mutex serializes acquisition with suspend/remove.
- Only the MFD-domain ADC virtual IRQ is enabled for a transaction. MIRQLVL1
  belongs to parent regmap-IRQ; GPIO/thermal/BCU/charger IRQs are untouched.
- W1C completion status is written only with this transaction's group bit.
  Other pending groups and the monitor-tick bit are not acknowledged.
- Conversion mask bits0–6 are owned. Probe refuses an unmasked unsupported
  monitor tick; bit7 is preserved.
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
