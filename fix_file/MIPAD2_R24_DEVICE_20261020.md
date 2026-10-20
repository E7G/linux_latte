# R24 physical delivery / camera cold-probe failure, 2026-10-20

## Result: candidate NOT qualified

6.14.0-mipad2-integrated-r24, built source130c1b76c1aa7761ac570f0342d6c6f77ad8497a,
was installed only into new versioned module/kernel directories. Exact archive,
module release, isolated initramfs, early USB unit/systemd verification and raw
GRUB/Btrfs byte comparisons passed. An append-only custom entry was selected
for ONE reboot. Saved bqdiag1 stayed unchanged and next_entry was consumed.
Actual USB serial and SSH reached R24; running config exactly equals the build,
and loaded AtomISP/front/rear/audio/Wi-Fi srcversions and installed bytes match
the manifest. Default Snapshot r6, private candidates and system plugins unchanged.

Cold probe is RED: T4KA3 register0x0000 read returned -121, the rear driver did
not bind, asynchronous graph completion never registered /dev/video0 or media/
sensor subdevices. First strict gate stopped in discovery (zero native capture
cases), and full read-only hardware smoke failed camera/VCM presence checks.
This is a real hardware-enumeration failure, NOT a Snapshot window symptom.

One later manual native drivers_probe write to the unbound rear device succeeded;
both sensors/VCM/video registered and existing OTP validation completed. This was
at boot second13745, versus the initial error at32.763 (~13712s later), NOT an
immediate retry or controlled proof of the root cause. No module replacement,
raw PMIC programming, persistent retry service or second reboot was used.
Successful reprobe does NOT turn the cold-boot result green.

## Real normal-path regressions AFTER reprobe

Four actual suites pass: both sensors' short and320-frame-per-phase long
multiopen/owner/takeover/STREAMOFF-ON plus streamparm ABI; cached-format reuse
and four lifecycle phases at30 and15fps for both sensors; silent PCM RT5659/
dual-TFA active/idle electrical checks before/after10s RTC; separate10s RTC
functional resume and9,058,304us S0I3 residency. Formats/mutable controls restored,
all final sensor/ISP runtime usage0/suspended. GPU200..600, original thermal guard
and anti-idle remained active; stable default/normal apps unchanged.
These are1280x720 YU12 native lifecycle/rate tests, NOT full1080p H.264 recording,
optical/Android quality, physical input interaction, sound-hearing or reset-fault
tests. Silent PCM is not an acoustic pass. Existing cold-probe error is retained
separately from zero BUG/Oops/GPU/SP-stop pattern counts in the later checks.

Exact gate sources are in tests/r24-device-gates; the streamparm source remains
tests/mipad2-streamparm-abi-test.c. Tests are version/device restricted and not
an automatic repair service. Actual scalar evidence, exact boundaries and host
fixture errors are in tests/mipad2-r24-device-validation-summary.json.

## Next: diagnose power/first-probe ordering rather than hide it

R19->R24 source comparison finds no change in the two sensor files, gmin helper
or CSI bridge. That does NOT prove R19 cannot have the failure or uniquely
attribute the cause elsewhere; probe ordering/ACPI/clock/reset need measurement.
Pinned [Xiaomi Android T4KA3 source](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/i2c/micam/t4ka3.c)
matches the retained local reference byte-for-byte. It sequences rail/clock,
GPIO release/reset pulse and bounded power/read attempts; the Linux ACPI port
has different sequencing. This is a hypothesis to test, not authorization to
copy obsolete GMIN PMIC operations into a modern ACPI driver or claim a fix.
Keep the initial failure and successful-later-probe timing in any comparison.

Before reboot,21 legacy scalar traces were copied byte-identically into persistent
tablet storage, old paths kept as root-owned aliases, and35 total mappings were
recreated after boot.29 remain user-readable; six originally root0600 stay
restricted. No raw traces, private media/cores or per-frame pixel digests published.

Still OPEN: clean cold-camera boot, headless boot reproducibility, SP/ISP stop/
reset/release physical DMA fence, applied-control recovery replay, full recording
cadence/quality, complete Linux+flash/OEM parity. R24 stays experimental; no
default promotion or completion claim follows from this post-reprobe pass.


Publication fixtures use LF line endings. Executed Windows-origin input hashes
are retained separately. Each Python AST is identical; all three C preprocessing
streams and newly compiled ELF hashes exactly match the actual hardware-test
binaries. Initial CRLF diff-check failure happened before any commit, not on
the device, and did not cause a repeated device test or weaker runtime gate.
