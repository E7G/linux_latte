# R25 Mi Pad 2 rear-sensor reset sequence candidate

This is a BOARD-ONLY production candidate, NOT a proven cold-boot fix. The
tablet still runs R24. Its original T4KA3 chip-ID read failed with -121 and
required one much later manual native reprobe; that result stays RED.
See MIPAD2_R24_DEVICE_20261020.md for actual observation and boundaries.

## Reference and mapping

Pinned [Xiaomi Android T4KA3 source](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/t4ka3.c)
matches the retained local reference byte-for-byte. After rails/clock it releases
powerdown, waits1ms, drives reset physical high/low/high with1ms intermediate
holds, then verifies ID. Linux previously released powerdown and reset together.

Actual tablet firmware CA27/TOSB0001 reports reset GPO1 pin52 and powerdown pin22,
both sensor-on-high. The existing CSI bridge correctly maps both ACTIVE_LOW;
logical0/1/0 therefore implements that physical high/low/high pulse. GPIO numbers
are NOT hardcoded in the driver. CAM3/front has a separate clock and shares some
ACPI rails. Both sensors' _DEP names the Whiskey Cove PMIC; PMIC/OpRegion native
drivers registered long before the failing camera probe, so a late handler is
not established as the cause. ACPI state alone is not a rail-voltage measurement.

## Minimal change

Only Xiaomi Inc/Mipad2 with ACPI companion and an available reset descriptor gets
the OEM pulse after powerdown release. Existing5ms initial delay and20ms final
settling/ID check stay; normal failure still returns the exact ID/I2C error and
asserts both available GPIOs. Other boards, absent-reset cases and suspend are
unchanged. NO automatic retries, forced ID success, PMIC writes, clock ownership
changes, new daemon, control reset, frame/bitrate reduction or queue workaround.
ACPI continues to manage shared rails and PMC clocks. This restores an OEM
sequence difference; it does NOT uniquely explain or prove the observed failure.

## Initial exact-source host evidence

Actual identity helper, chip-ID detection and PM suspend/resume functions were
compiled with ASan/UBSan/leak checks against GPIO/CCI/delay/ACPI/DMI stubs and an
independently specified ordered OEM sequence.4608 identity/ACPI/GPIO-presence/
polarity/error/repetition cases,102912 resume calls per variant,268 successful
physical-polarity pulse checks: old has144 sequence mismatches, candidate0.
This is a synthetic sequence contract, NOT4608 real sensor tests or a reproduced
electrical NACK. Success, high/low-register -121, timeout, wrong ID and unsupported
I2C propagation/cleanup are covered;1/2/64 repeated wake/suspend calls checked.

Required next gates: all prior exact-source suites, W=1 focused/full build,
isolated signed delivery, controlled physical cold starts and warm/stream/
suspend regressions with original failures retained. Full reset/DMA ownership,
applied ISP-control replay, full recording cadence/image quality and complete
kernel+flash/Android-Windows parity remain open. No deployment qualification.


## Completed offline regression gates

All28 exact-source host suites exit0, including prior recovery/ownership/ABI
models and the new4608-case current-source pulse contract. W=1 Clang21/LLVM
prepare/modules_prepare/t4ka3.o compile passes in an isolated R25-focused output;
config differs only by LOCALVERSION. R19/R20/R24 five build artifacts each and
the original dirty litmus remain unchanged. Source stayed fixed throughout.
See tests/mipad2-r25-reset-validation-summary.json for exact hashes and scope.

The eight actual ACPI table checksums are valid. Combined iasl disassembly hit
duplicate CPU SSDT objects (exit255); standalone DSDT disassembly exits0 while
retaining unresolved external warnings. Raw PR0 AML confirms the five rear and
four front resource references; cosmetic doubled disassembler commas are not
extra package elements. No table override or ACPI/PMIC write was performed.
This inspection does not certify all firmware semantics or establish the cause
of the first probe failure. Physical cold-boot testing of R25 is still REQUIRED.
