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


## Actual R25 build and first-device qualification (2026-10-20)

The completed Clang21 W=1 full bzImage/modules build uses source
11d2680b7773cd46d5dc4513be7b31bd99f124b5. All three build phases exit0;
only LOCALVERSION differs in configuration. The source, original dirty litmus,
and R19/R20/R24 protected artifacts stayed unchanged. Existing compiler warnings
remain in private build logs. The 20,902,938-byte archive has SHA256
0b8d43e9f0f9b3c3f73e75285fc04e2c50f68aa836a98f76fa9016003dadb24b.
All52 regular files,34 compressed modules, embedded configuration, and each
CMS module signature against the actual build certificate were verified.

One warm machine reboot reached R25 with matching running configuration and
five loaded native module identities. Both sensors and rear VCM registered on
the first probe with no sensor-read/probe error, rebind or module reload.
This is one fresh-kernel first probe, NOT S5/removal-of-power qualification or
proof that the OEM pulse uniquely caused the improvement over R24.
The stable bqdiag1 GRUB default and existing application/default are unchanged.

### Real narrow gates and retained failures

Both inputs pass native strict multiopen/takeover/ordinary restart, a separate
320-frame-per-phase variant, streamparm ABI, and four cached-format phases at
30 and15 fps (1280x720 YU12; mean period within1%). Mutable controls and sensor
shapes are restored. A new real strict run after all five RTC cycles also passes
on both inputs. These native gates are NOT full1080p H264 cadence, optical
quality, automatic exposure/WB/focus, or end-user parity measurements.

Silent zero-PCM RT5659/dual-TFA active/idle electrical checks before/after RTC
pass. No tone was played; no new audible/acoustic verification is claimed.
The audio run enters S0I3 for9.086368s. A separate10s RTC run resumes correctly
but has ZERO S0I3 residency: the strict coordinator rejects it. This real deep
power failure remains RED despite the child script's functional-resume exit0.

A controlled same-boot host COM17 reader OFF/managed-ON/OFF comparison gives
9.521760s /0 /9.185856s S0I3. All RTC wakes and driver suspend/resume callbacks
return successfully; no pending-wakeup/early-abort line is observed. Only the
owned Windows serial reader changes; cable, kernel and power policy do not.
The observer is closed afterward. This supports a USB-debug-observer/standby
interaction, not a complete root-cause proof or permission to suppress logging,
disconnect USB, or rewrite the failed acceptance gate as green.

Two harness problems are separately retained: the first severity regexp matched
the suffix of `debug:` as `BUG:`; the same full saved boot log was reclassified
using word-boundary severity markers with actual kernel BUG forms retained.
The published four-group fixture passes in normal and optimized Python modes.
The original generated audio helper had stale parent/source identity assertions
and failed BEFORE PCM or RTC; a new corrected helper ran once. Native passes
were not repeated just to repair bookkeeping. Private original reports remain.

Final read-only checkpoint: both sensors and ISP suspended with usage0, controls
restored, thermal guard and anti-idle active, GPU200..600MHz, no trace instances,
35 private scalar aliases intact, protected software/default unchanged.
Only explicit scalar summaries are published. No raw media, request/pointer
traces, serial contents, or firmware dumps are included.

See tests/mipad2-r25-device-validation-summary.json. Normal qualification is
PARTIAL. Active-debug deep power, power-off cold-boot reliability, physical DMA
stop/reset fencing and full recording cadence remain open. The integrated
kernel/flash/OEM-parity objective is NOT complete; no stable-default promotion.
