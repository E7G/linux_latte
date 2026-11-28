# Mi Pad 2 7.2 early x86 boot ISA

The Mi Pad 2 kernel is tuned for Airmont (Silvermont ISA selection). The
EFI stub and decompressor are separate freestanding programs; they run
before the regular kernel has a chance to check CPU features. Unlike
the main kernel, their 7.2 x86-64 flags did not explicitly constrain the
compiler target. A distribution's compiler default must not silently
introduce instructions that the Mi Pad 2 does not support.

Bring the baseline x86-64 target from CachyOS commit
7f2cd26d49c9224b43225655e3070e684ab61403 into 7.2 only. Do not change the
32-bit flags, the 7.2 normal Silvermont target, or the older CachyOS branch.

The Actions test uses a compiler wrapper that prepends an x86-64-v3
default. Kbuild's final target must override it in the actual cached
compile commands for an EFI stub object, a decompressor object, and a
regular kernel object (generic x86-64, generic x86-64, and Silvermont,
respectively). OVMF then boots the exact resulting 7.2 bzImage into a
small initramfs. The guest checks that it was booted by EFI and that
it exposes no AVX/AVX2 or BMI1/BMI2, then mounts a disposable Btrfs
filesystem read-only and confirms its marker before shutdown.

This is a synthetic x86-64 CPU compatibility check, not a test of
production Secure Boot, physical firmware, or eMMC. The guest has no
host disk and no network. It does not install the CI kernel or change a
tablet's saved boot entry.
