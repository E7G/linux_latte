# Mi Pad 2 7.2.15 charger-source hardware qualification

2026-11-28, the existing physical Mi Pad 2. Candidate source:
`623f2df1d84922f3a3db9ac4468e6123f6f4c793`. It includes the type
reporting/notification change from [PR #102](https://github.com/E7G/linux_latte/pull/102)
and not the separate suspend/HiZ change in [PR #103](https://github.com/E7G/linux_latte/pull/103).

- [Full build 46115929266](https://github.com/E7G/linux_latte/actions/runs/46115929266)
  produced release `7.2.15-mipad2-integrated-charger-ci`, kernel SHA-256
  `e7fcbff49816c1f21fe8667cab035b7e5a43b3452c07f744d6f1e60f5a224852`.
  The artifact manifest, source, config and archive were rechecked after
  download. All 37 module CMS signatures were independently verified;
  the tampered-module negative control was rejected.
- [UEFI run 46118310296](https://github.com/E7G/linux_latte/actions/runs/46118310296)
  booted those bytes once, actually loaded 11 signed modules with enforcement,
  consumed the one-shot entry and then booted LPAT31 with unchanged saved
  defaults. This was a virtual boot/fallback test, not charger emulation.
- The tablet's GRUB read back the staged image and initramfs byte-for-byte.
  The physical tablet reached the new release and matched the staged kernel
  digest and source. Module signature enforcement was active, nine loaded
  board modules matched their installed versions, no system units were
  failed, and the serial gadget and native audio routes returned.
- The *same connected PC port* remained SDP at 500 mA. The BQ25890 charge
  regulation readbacks stayed at 4,400,000 µV and 2,048,000 µA. These are
  configured limits, not measured current into the battery. The gauge
  continued to report net discharge during the test. No settings were
  written to either power-supply device.
- A second normal reboot returned to LPAT31. The saved GRUB environment
  and all pre-existing menu entries were byte-identical. The new entry is
  optional with no pending one-shot. USB serial was present, the Btrfs
  device error counters stayed zero and the installed camera launcher and
  native-AE binary matched their prior hashes. No 6.14 files were changed.

This passes the physical boot and known-SDP regression, not physical DCP
or unknown/non-standard classification. The tested connected source did
not change. Those type transitions and type-only notifications passed the
modeled register tests; they have not been reproduced on the tablet with a
separate adapter. No suspend, RTC wake, or power-saving claim is implied.
