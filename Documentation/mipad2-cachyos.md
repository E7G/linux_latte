# Mi Pad 2 CachyOS branch

The `cachyos-mipad2` branch keeps the device support from `main` and carries
the performance patch set in the kernel source itself. Image builders must
compile `xiaomipad2_defconfig` directly and must not apply a second copy of
the CachyOS or BORE patches.

The profile targets the Cherry Trail/Airmont SoC and 2 GiB memory limit:

- Silvermont compiler target, LLVM ThinLTO and `-O3`;
- BORE with 300 Hz preemption for interactive latency without a 1000 Hz idle
  power penalty;
- schedutil, MGLRU and zram for bursty tablet workloads;
- BFQ/ADIOS support for the internal eMMC;
- compressed modules and an explicit `-mipad2-cachyos` release suffix.

Device drivers keep the Mi Pad 2 configuration from `main`. In particular,
BCM4356 Wi-Fi and Bluetooth remain modules so their ABI always matches the
running kernel.
