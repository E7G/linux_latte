# Mi Pad 2 7.2: evidence after a failed boot or resume

Once the tablet is reachable again, use the read-only EFI crash summary on the
tablet. The external systemd archive is normally root-readable only:

```sh
sudo python3 fix_file/tests/mipad2-pstore-report.py
```

This does not mount filesystems, clear records, write firmware variables, or
print journal/pstore contents. It looks at an already mounted `/sys/fs/pstore`
and at `/var/lib/systemd/pstore`, including systemd's EFI timestamp/count
subdirectories. The [systemd pstore service][systemd-pstore] may archive and
unlink the live record before login. Identical copies are counted only once in
`efi_groups`; the per-source `records` counts are independent.

- `observer_boot_id` and `observer_kernel_release` identify the running recovery
  boot, not the previous boot that wrote a crash dump. For each group compare
  `record_epoch_seconds` to the incident time in UTC. The wall clock may be
  wrong or unset, and retained records may be from a different incident.
  `dump_count` is the EFI record ID's counter field, not the number of incidents.
  One dump may cross a wall-clock second and appear in multiple groups.
- A `panic` / `oops` / `emergency` / `shutdown` counter denotes chunks with that
  kernel dump header, not how many crashes occurred or what caused them.
  `compressed` and `unknown` chunks were present but not classified.
- `partial` or `unreadable` means a bounded scan missed or could not read some
  evidence (exit 2). `not-mounted`, `missing`, and `empty` are distinct. Do not
  interpret them as proof of a clean boot: a hard lock, early halt, power loss,
  EFI runtime failure or journal-only systemd configuration may leave no
  readable files. This helper does not inspect the journal. Record the observed
  screen state and whether network/TTY came back separately.

[systemd-pstore]: https://www.freedesktop.org/software/systemd/man/latest/systemd-pstore.html
