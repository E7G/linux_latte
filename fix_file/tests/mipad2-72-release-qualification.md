# Mi Pad 2 7.2 combined qualification

## Exact inputs and repeatable tests

The combined candidate is kernel commit
`603f99209cba3fc41e697890f980f68873f94c52`. It includes the release module
coverage, onboard Wi-Fi/Bluetooth and touch checks, USB gadget availability
guard, and default-off PMC observation trace. The optional virtual GPIO
experiment is not included.

- [Full source build](https://github.com/E7G/linux_latte/actions/runs/46109996857):
  37 module signatures verified against the build's public certificate; a
  corrupted payload was rejected. The PMC trace is linked into vmlinux.
- [UEFI one-shot test](https://github.com/E7G/linux_latte/actions/runs/46112553508):
  exactly one candidate boot, 11 module loads under enforcement, then LPAT31.
  GRUB consumed the trial entry and kept its saved default. Firmware Secure
  Boot was not enabled for this VM.

Run the full build again from the qualification branch:

```sh
gh workflow run mipad2-72-release-config.yml -R E7G/linux_latte \
  --ref codex/mipad2-72-hardware-qualification -F full_build=true
```

Once that run publishes its artifact, pass the actual run ID and recorded
head SHA to the UEFI test:

```sh
gh workflow run mipad2-72-release-config.yml -R E7G/linux_latte \
  --ref codex/mipad2-72-hardware-qualification -F boot_test=true \
  -f candidate_run=RUN_ID -f candidate_sha=EXACT_HEAD_SHA \
  -f fallback_run=46004200827
```

The fallback run must publish the pinned LPAT31 replay. If its artifact has
expired, dispatch the LPAT31 replay again and supply its new run ID.

## Physical tablet, 2026-11-28

One isolated trial booted the exact verified candidate, using the tablet's own
initramfs tooling and an unchanged LPAT31 serial-console hook. The trial
consumed `next_entry` while keeping LPAT31 in `saved_entry`. A second
reboot, with no entry armed, booted LPAT31 again and returned the GRUB
environment to the same bytes as before the trial.

On the candidate, module signature enforcement was active. The PMC event
exposed the six expected fields and was disabled by default. The physical
Wi-Fi, Bluetooth UART and FTSC1000 multitouch device were correctly
identified. USB gadget enumeration and the RT5659 speaker and internal
microphone routes were present. Nine running Wi-Fi/Bluetooth, camera, audio
and power-monitor module source versions matched the candidate. There were
no failed system units or Btrfs device errors in either postflight.

These are boot, binding, and routing checks. They do not prove Bluetooth
pairing, camera image capture, analog headset insertion, Secure Boot, or
successful system sleep/RTC wake. The root filesystem's pre-existing
USB service was not replaced by this trial; it does not prove the new
service path on a machine without a UDC. LPAT31 remains the physical default.
