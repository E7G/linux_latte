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
