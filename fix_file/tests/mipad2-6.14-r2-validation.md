# Mi Pad 2 6.14 r2: verified state, 2026-10-05

This is an integration candidate, not complete hardware acceptance. No changes
were made to 6.18. Stable GRUB default remains `mipad2-bqdiag1`; candidate entries
use `grub-reboot` once. Keep the anti-idle service active during remote tests.

## Kernel and USB handoff

- Runtime: `6.14.0-mipad2-integrated-r2`, built from
  `b1f68fb71c0936ee5d8f2e59faf7aae903dddfbc` with Clang 21.1.8.
- Kernel SHA-256:
  `c0edbb6d09a93edf46c3d2a72b8e0118a4bf638482141c14730807bada7f4734`.
- Direct-root and normal systemd initramfs boots were observed independently.
- Verified early-serial boot ID:
  `66ccb8d8-c1a7-46d8-93d7-866de18805a5`.
- Candidate-only serial initramfs SHA-256:
  `6abf32d7144cbc5f5b1d02f8b862ed9d965617e640ebc98c858792ef6c497716`.
  This diagnostic image is not installed by the ordinary USB helper package.
- Command line: `console=ttyGS0,115200n8 console=tty0`. `/proc/consoles`
  confirms ttyGS0 enabled and tty0 preferred for `/dev/console`.
- Kernel-clock proof: early helper BEGIN at 88.565815 s, UDC BOUND at
  88.593845 s, first Btrfs root mount at 89.470894 s. The initrd journal
  independently confirms successful service execution. Do not compare these
  kernel timestamps numerically with systemd journal timestamps.
- Root helper logged `preserving serial connection`, rather than rebinding
  the UDC. Windows COM17 received initrd root-mount and switch-root output.
- Hardware enumeration smoke, all 26 loaded modules' release/srcversion, and
  the running versus staged kernel configuration passed on this boot.

The first early-serial image contained `sys-kernel-config.mount` but omitted
`modprobe@.service`. Its start transaction failed offline verification because
`modprobe@configfs.service` could not be found. This mkinitcpio version's
`add_systemd_unit` looks up literal unit filenames, not instance templates.
The isolated replacement hook explicitly adds `modprobe@.service` and the
modprobe binary. Extracted-image `systemd-analyze verify --man=no --root=...`
then passes for both `initrd.target` and the candidate service. Original images
were retained. This establishes a real defect, not the unique cause of the
earlier unobserved boot failure.

## Helper package regression

USB helper pkgrel 3 preserves an already-bound matching ACM gadget, checking
UDC, VID/PID, function directory and configuration link. Explicit stop and
suspend still detach. Eight hardware-free guard tests pass. Six native Arch
packages pass all 24 source verification, clean-build, source archive and clean
source-roundtrip checks, including identical installed payload paths/hashes.
Those built test packages were not installed; the new USB helper alone was
backed up, tested on the live already-bound path and deployed for this boot.

## Open gates

- Current r2 physical sound and rotation acceptance, sustained usage, and
  cable-unplugged boot remain unverified. Prior user listening and four-way
  rotation results belong to earlier 6.14 tests, not automatically this boot.
- Camera capture/OTP checks pass, but color and 3A are not accepted.
- Generic TFA989x remains selected; factory DSP is not the default and still
  needs acoustic, profile, concurrency and sustained-resume acceptance.
- UBSAN signed-wrap reports were observed in atomic fallback and x86 atomic
  add-return paths. Clang's documented signed-overflow checking still runs
  with `-fwrapv`; an isolated Clang21 reproduction confirms this behavior.
  A narrow no-sanitize annotation suppresses only the intentional-wrap test
  while the unrelated bounds control still reports. **No kernel annotation,
  global sanitizer disable or runtime warning suppression has been applied.**
  The actual call sites still need review before any source change.
- Verbose console/initcall diagnostics are enabled; these boots do not
  establish production startup performance or long-term stability.

References: [kernel console semantics](https://www.kernel.org/doc/html/latest/admin-guide/serial-console.html),
[kernel atomic wrapping contract](https://www.kernel.org/doc/html/latest/core-api/wrappers/atomic_t.html),
[Clang signed-overflow checks](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html).
