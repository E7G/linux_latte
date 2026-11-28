# Mi Pad 2 7.2 BQ2589x source classification

The issue is charger identification and notifications, not the battery charge
policy. On LPAT31, the built-in driver's `model_name` reported BQ25890. On the
computer's USB port it reported SDP and a 500000 uA input limit; the fuel gauge
and UPower reported net battery discharge. The charger's internal charge-phase
status was simultaneously Charging. These are different measurements: an
online port can supply some system load without charging the cell.

## Reference behavior

- TI [BQ25890/BQ25892](https://www.ti.com/lit/ds/symlink/bq25890.pdf),
  REG0B and table 9-3, and [BQ25895](https://www.ti.com/lit/ds/symlink/bq25895.pdf),
  REG0B: status 5 is an unknown adapter with a 500 mA initial limit, and
  status 6 is a non-standard divider. Neither is a confirmed BC1.2 DCP.
  Status 4 remains DCP because the chip identified a high-voltage DCP; that
  classification does not request a different VBUS voltage.
- The [factory Android charger driver](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/78fbd35b6c73ee51129d690c4306f320e40a1401/drivers/power/bq2589x_charger.c#L1748-L1828)
  also distinguishes unknown and non-standard inputs from confirmed DCP
  internally. Its legacy type is DCP for those cases, but its cable event
  gives them the SDP current, not the confirmed DCP current. Linux reports
  `USB_TYPE_UNKNOWN` instead of preserving the misleading DCP label. The
  supplier property path for BQ25892 and the conservative BQ25896 reporting
  are unchanged.
- TI documents a source-detected IRQ separately from power-good. Decode
  VBUS type, charging state, power-good and minimum-system-voltage state
  from the same REG0B read in the IRQ snapshot. A type-only change now
  reaches `power_supply_changed()` even with unchanged power-good. A
  transition between two codes with the same exported type does not emit
  an extra event. The live `usb_type` read still propagates I2C failures.

The change does not program USB detection, input current, charge voltage,
charge current or battery termination settings. HiZ restoration and ADC
rate changes on real online/offline transitions retain their prior behavior.

## Qualification

The host test compiles the production decoder, live getter, state read and
IRQ handler. It covers all 256 REG0B byte values on each of the four chip
variants, all 64 type transitions per variant with PG and charging fixed,
I2C read and write errors, and cable/forced-HiZ ADC transitions. The CI job
also compiles the built-in object with the Mi Pad 2 x86 config.

Physical acceptance still needs a one-shot boot of a signed 7.2 build and
selected sources: the existing PC SDP, a known dedicated supply, and an
adapter independently known to report an unknown/non-standard class. Compare
reported type, input limit, UPower state and power-supply uevents on connect
and disconnect. A physical change of type without PG dropping is not assumed
to be reproducible by moving cables; that path is covered by the host test.
Do not infer measured adapter capability from the charger type alone.

## Independent system sleep follow-up

The TI data sheet's battery-monitor section notes that its automatic
once-per-second conversion can increase quiescent current. The driver
normally enables continuous conversion only with power-good and without
HiZ, but previously a suspend-time IRQ could undo the pause and resume
checked only power-good. Resume also wrote the shared state during a
multi-read transaction, and could expose a partially refreshed snapshot
if any later I2C operation failed.

Serialize the ADC pause, HiZ request and status changes. A cable IRQ
while suspended must not restart periodic conversion. On resume, apply the
existing online/HiZ policy to a fresh snapshot; if the cable was replugged,
reapply an outstanding user-requested HiZ before restarting the ADC.
If the read or write fails, preserve the prior snapshot and finish the
restore on the next successful status refresh, even if the status bytes
are identical. Do not change charge limits or the ADC one-shot API.

The host test also drives the real suspend/resume callbacks with modeled
I2C failures and cable IRQs, checks the ADC and HiZ writes, and rejects
duplicate or premature change notifications. This is not a hardware power
or sleep result. Measure actual wake, charger state and PMC residency
on a separately authorized RTC suspend cycle before promoting the follow-up.
