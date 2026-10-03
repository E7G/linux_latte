# Mi Pad 2 CachyOS branch

The `cachyos-mipad2` branch is the device-kernel source of truth for the
Mi Pad 2 release. It carries the board support and performance patch set in
the kernel source itself. The `main` branch may diverge; do not assume changes
there affect the tablet image until they are explicitly ported to this branch.
Image builders must compile `xiaomipad2_defconfig` directly and must not apply
a second copy of the CachyOS or BORE patches.

The profile targets the Cherry Trail/Airmont SoC and 2 GiB memory limit:

- Silvermont compiler target, LLVM ThinLTO and `-O3`;
- BORE with 300 Hz preemption for interactive latency without a 1000 Hz idle
  power penalty;
- schedutil, MGLRU and zram for bursty tablet workloads;
- BFQ/ADIOS support for the internal eMMC;
- compressed modules and an explicit `-mipad2-cachyos` release suffix.

Device drivers in `cachyos-mipad2` keep the Mi Pad 2 configuration. In
particular, BCM4356 Wi-Fi and Bluetooth remain modules so their ABI always
matches the running kernel. The active image branch pins this kernel source to
an exact commit before building.

The device defconfig enables `CONFIG_CPU_MITIGATIONS=y` by default. Do not
append `mitigations=off` in normal use: the kernel documents it as disabling
all CPU attack-vector mitigations. Reserve that boot option for controlled
performance comparisons only.
