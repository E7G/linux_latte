# R27 device checkpoint, not final qualification

2026-10-22. Built from `ef89fc60f8d5f1accd221e3c28f7e2ae6678bb72`.
This is a documentation/evidence update; it does not change compiled kernel code.

## Delivered and measured

- Full bzImage/modules build completed successfully. Configuration differs from
  r26 only in LOCALVERSION. Generic W=1/kernel-doc warnings remain; only the
  separately focused T4KA3 build had zero warnings.
- All 34 compressed modules passed detached CMS verification against the pinned
  public build certificate. The real makepkg/ALPM repack preserves 52 bundle files
  and verifies all 56 package payload files. Host and tablet pacman queries pass;
  the ALPM package was NOT installed. No private signing key is in the package.
- One warm reboot reached r27 with exact config and loaded-module identity.
  Both native sensors and VCM bound on their first probe, without reloading or
  manual reprobe. This is not an S5/removal-of-power cold-boot qualification.
- Both cameras pass strict queue ownership, long restart and stream-parameter
  checks. Native queue delivery is approximately 30/15fps across observer close,
  ordinary restart and remaining-fd takeover. This does not qualify new-source
  Snapshot recordings, encoded-frame conservation or Android optical parity.
- Actual V4L2 control-framework tests advertise exposure minimum one. With a
  two-line unbinned crop, minimum VBLANK is five and exposure range is [1,1];
  VBLANK six changes the range to [1,2]. Range endpoints work. Tiny geometry was
  never streamed. All original controls and geometry were restored.
- Legacy S_CTRL requesting zero succeeds with readback one (clamping), not
  ERANGE. The first ad-hoc test incorrectly required ERANGE and failed; its
  receipt is retained. Correcting that expectation required no driver change.
- Silent audio electrical checks and RTC functional resume pass. No tone was
  played. Final ISP/sensor runtime PM is suspended with usage zero, 274 protected
  files are unchanged, and 53 private trace aliases are restored.
- Existing no-idle service stays active and native Denial automatic DPMS remains
  disabled. Thermal guard and original authentication/foreground behavior remain.

## Open power gate: do not promote this checkpoint to default

The first audio RTC trial accumulated 9,679,456us S0I3. The following normal
RTC trial resumed correctly but accumulated zero S0I3. After an explicit 20s idle
settlement, a fixed three-trial cohort produced zero, 9,526,464 and 9,491,232us.
The original failure remains a failure; later passes do not overwrite it.

A separate fixed USB-bound / unbound / bound cohort (two trials per phase) had
six nonzero S0I3 samples, including the bound phases. Binding was restored and
USB returned to configured. The host SSH reply reset, but the same device-side
job completed all six trials and its scalar receipt was recovered; it was not
restarted. Temporary unbinding followed the documented
[configfs gadget interface](https://www.kernel.org/doc/html/v5.10/usb/gadget_configfs.html).
This does NOT establish USB causality or resolve the intermittent zero-residency
condition. Related r25 diagnostics also contain zero-residency observations.
No speculative PMC/clock/charger/GPIO policy patch was applied.

The stable saved GRUB default remains bqdiag1 and next_entry is empty. r27 is
currently running only because of the single selected test boot. Further
power diagnosis, new-source app foreground/recording tests, native photographs,
scene-dependent AE/AWB/AF, full-image build/boot and broader Android/Windows
hardware qualification remain open.

Software/scalar [machine-readable evidence](tests/mipad2-r27-device-checkpoint-summary.json)
contains no raw serial, frame, buffer-pointer or source-thread traces.
