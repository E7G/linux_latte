# Mi Pad 2 7.2 charger and sleep-state preview

This branch retains the already tried USB source classification candidate
and adds the combined REG0C fault snapshot and HiZ/ADC recovery fixes.
The code-only integration is commit
74b106f26fb4ac5b2d62407dd054d66a88be9555.
[Run 46123854198](https://github.com/E7G/linux_latte/actions/runs/46123854198)
passed GCC and Clang modeled-I2C tests plus a built-in-object build with
the 7.2 Mi Pad 2 defconfig.

It has a separate kernel release, 7.2.15-mipad2-integrated-charger-pm-ci,
so its CI bundle cannot be mistaken for the earlier charger trial.
Start the complete build (without a connected device):

    gh workflow run mipad2-72-release-config.yml -R E7G/linux_latte --ref codex/mipad2-72-charger-pm-preview -f full_build=true

A successful build can be followed by the isolated UEFI one-shot test.
Pass that run's numeric ID and exact commit SHA as candidate_run and
candidate_sha, with boot_test=true and the same branch. The workflow
verifies CI provenance before downloading either boot input.

There is no physical fault, sleep or AC adapter qualification for this
revision. No installation, default boot entry or system image changes
are made by building the candidate.

## Exact cloud artifact and UEFI rollback

[Full build 46124167682](https://github.com/E7G/linux_latte/actions/runs/46124167682)
compiled kernel source 1bea49a060f00c1414a5212249258f900f6d84a0.
Its bzImage SHA-256 is
64d52e7ee28c5febfea76eaa19f070de0982b5a5fc057773883c27ee57e0c021.
All eight manifest inputs passed independent checksum verification.
The downloaded module archive was also independently verified against the
run's public certificate and matching kernel release: 37 valid signatures
and one rejected modified payload. The generated verification JSON exactly
matched the GitHub artifact.

[UEFI run 46126749250](https://github.com/E7G/linux_latte/actions/runs/46126749250)
booted that exact candidate in a VM, loaded 11 signed modules, and confirmed
the PMC trace stayed off by default. A second boot selected the pinned
LPAT31 fallback. The serial markers and GRUB environment show the
candidate entry was consumed once; saved_entry stayed unchanged.

This is VM boot and rollback evidence only; it does not verify charger
hardware, actual suspend/resume, or a wall adapter. The physical tablet
remains on its existing LPAT31 default. Rebuild from source if the
published artifacts expire; signing identity is per build.
