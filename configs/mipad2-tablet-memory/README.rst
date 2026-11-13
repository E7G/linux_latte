Conservative tablet working-set protection
==========================================

This is a Linux-native configuration inspired by mobile memory-management
principles, not a port of iPadOS/XNU or a complete application lifecycle manager.
It adds no persistent daemon and imposes no new application memory caps.

Prerequisites and installation
-----------------------------

Verify CONFIG_LRU_GEN, enabled MGLRU and cgroup v2 memory_recursiveprot.
The tested MiPad2 user UID is1000. Adjust the slice name for other systems.
Back up existing configuration before installation. Copy the two slice drop-ins
to corresponding /etc/systemd/system/UNIT.d/ paths. Copy the tmpfiles file to
/etc/tmpfiles.d/60-mipad2-memory.conf. Reload systemd; apply MemoryLow=192M
to existing user.slice and user-1000.slice with systemctl set-property --runtime.
Apply the exact tmpfiles configuration, not unrelated system-wide changes.

MemoryLow is best-effort reclaim protection, not192MiB reserved per application.
The parent user.slice budget and the UID slice budget are hierarchical, not
additive. With memory_recursiveprot enabled, descendants share that budget.
Protection can be breached to avoid OOM. It is not an OOM exemption.

min_ttl_ms=1000 protects the most recent one-second working set from eviction.
If that working set exceeds available memory, the kernel can trigger OOM rather
than thrash; larger values are deliberately not used here. Revert to0 if workload
testing shows premature OOM. No system-wide OOM stress test was performed.

Existing compression and Android policy
--------------------------------------

Keep the already-installed one-RAM-size LZ4 zram device, swappiness160,
page-cluster0 and disabled zswap; these were existing settings, not gains
introduced by these files. Do not swapoff/reset a live zram device just to
change compression. Do not stack zswap over zram or periodically drop caches.
Android's existing lmkd remains responsible for Android application priorities.
This configuration does not freeze arbitrary host applications, promise dynamic
per-window foreground detection, or add a second competing background killer.

Validation and rollback
-----------------------

On7.2 daily2 an isolated64MiB anonymous allocation was tested in its own bounded
service. Requesting32MiB through that service's memory.reclaim moved33320960bytes
into swap, with a matching decrease in resident charges. Full checksum readback
passed; no host OOM event occurred, desktop PID remained unchanged and Android
remained ready. This establishes reclaim/compression data integrity, not a
matched before/after performance improvement or long-term pressure qualification.

For rollback, restore previous slice MemoryLow values and min_ttl_ms, remove only
these installed drop-ins/tmpfiles configuration, reload systemd and restore the
runtime properties too. Do not touch Android data or the active zram device.

References
----------

https://docs.kernel.org/admin-guide/mm/multigen_lru.html
https://docs.kernel.org/admin-guide/cgroup-v2.html
https://docs.kernel.org/admin-guide/blockdev/zram.html
https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_memorystatus.c
