# R24 offline kernel delivery bundle,2026-10-20

Release6.14.0-mipad2-integrated-r24, built source
130c1b76c1aa7761ac570f0342d6c6f77ad8497a. Full build/parameter-owner lifetime
fix evidence is separate in MIPAD2_R24_RESET_PARAMS.md. This adds delivery
packaging verification, NOT hardware/deployment qualification.

Archive mipad2-6.14-integrated-r24.tar.zst,20898799bytes, SHA256
66747643319bbe4183e884e42b207c6e29d4f8086fc199039b2bd6d8c292a329.
The package contains only versioned modules and versioned kernel/config/System.map/
manifest under usr/lib/modules and var/lib/mipad2-kernel; no installed boot entry,
initramfs, native images/media, keys, symlinks or special files. It stays local,
not uploaded as a binary or copied to the tablet by this packaging operation.

Verified actual bzImage HdrS/version banner, embedded config exactly equal to
the completed build, unchanged R19 config except LOCALVERSION, same34 module
names as R19, every installed module's release/vermagic and signer serial, and
each detached module CMS signature against ONLY this build's certificate.
Original34 built .ko files and five build artifacts were unchanged by packaging;
R19/R20 protected artifacts and user's dirty litmus file retained. Integration
commit at packagingd7c2dfb7ae2032055e30c17c0aa1f3e7addebb86 was remote verified.

A separate streaming decompression/tar audit then re-read the ACTUAL archive:
52 regular files including manifest, no duplicate/absolute/traversal/link/special
entries, every file hash matches manifest, boot files match the completed build.
Full validation scalars/hashes are adjacent in tests/mipad2-r24-bundle-verification-summary.json.
No source tree reset or modifications to previously tested kernel artifacts.

The tablet remains R19 on its unchanged boot/default. R24 is NOT staged,
installed, booted or subjected to hardware fault injection here. Physical ISP/SP
stop/reset DMA ownership, recovery control replay, regular hardware/PM regressions
and the original complete Linux/flash/Android-Windows parity objective remain
OPEN. Before experimental one-shot boot, preserve the proven fallback and verify
serial/recovery, exact source/artifact/target/free-space/GRUB guards; do not treat
compilation or cryptographic packaging as a safe DMA fence.
