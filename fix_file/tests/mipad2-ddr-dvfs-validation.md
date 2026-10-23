# AtomISP DDR DVFS mailbox error handling (7.2 candidate)

## Evidence and actual change

The requested upstream `9928c7b8d00c500ee97903afa1cc76c1c36ab2bc` contains a
void DDR helper that ignores both IOSF results and does a read/modify/write
across separate mailbox lock acquisitions. A failed read can leave an undefined
register value; writing it is not a valid recovery. Another mailbox client can
also update unrelated bits between those calls and have its update overwritten.

Use the existing `iosf_mbi_modify()` instead: its actual implementation holds one
mailbox spinlock over both operations, checks the read result before consuming
it, and returns the write status. The bit0/bit1 mask and successful request
values remain unchanged. No new register bits or hardware delays are invented.

On Cherry Trail power-on, disabling DDR DVFS is the existing workaround's
precondition. Propagate a failed mailbox operation **before** the 20 ms delay
and IUNIT power request. Preserve its actual errno, not a synthetic timeout.

On power-off, the existing OEM sequence has already submitted the IUNIT off
request before re-enabling DDR DVFS. Log a failed DDR operation, but **continue
observing the already-live power request's acknowledgement**. Do not return
early and leave the PCI/PM power-state cache inconsistent with a subsequently
powered-off IUNIT. Successful power acknowledgement remains the primary return
condition; status-transport errors and real acknowledgement timeouts retain
their own errno. A warning is not a claim that DDR DVFS was restored.

## Reference comparison, not blind transplantation

* [Requested Linux source](https://github.com/E7G/linux_latte/blob/9928c7b8d00c500ee97903afa1cc76c1c36ab2bc/drivers/staging/media/atomisp/pci/atomisp_v4l2.c)
  has the unchecked split IOSF RMW used as the regression baseline.
* [Mi Pad 2 Android source](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_v4l2.c)
  retains DDR-disable-before-power-on and DDR-enable-after-off-request ordering.
  Its old msgbus transport and doorbell bit differ; its polling `if` has a stray
  semicolon. Copying that loop does not provide a working acknowledgement check.
* No Windows source-level DDR/DMA ordering is presumed from driver binaries.
* [Linux PCI guidance](https://docs.kernel.org/PCI/pci.html) requires DMA to stop
  before its memory is freed. Local `drivers/pci/pci.c` shows that
  `pci_wait_for_pending_transaction()` returns success without testing anything
  for non-PCIe devices. Do not add it as a pretend generic IUNIT DMA fence.

## Reproducible host contract

```sh
python3 fix_file/tests/mipad2-ddr-dvfs-host-test.py
python3 fix_file/tests/mipad2-ddr-dvfs-host-test.py --expect-red --mutation swallow-on-error
python3 fix_file/tests/mipad2-ddr-dvfs-host-test.py --expect-red --mutation split-rmw
python3 fix_file/tests/mipad2-ddr-dvfs-host-test.py --expect-red --mutation abandon-off-ack
```

The test compiles the **exact** DDR helper, IUNIT power function and three IOSF
public mailbox functions. Only their PCI mailbox endpoint, clock, logging and
lock interleaving are synthetic. 196,608 DDR cases cover both values of the
enable flag, diverse unrelated register bits, read/write errors and an explicit
second-mailbox-client interleaving. 280 power cases cover Cherry Trail/non-CHT,
PM-only/full mode, both power directions, request/DVFS/status errors and timeout.

The old source fails 172,032 helper and 20 power cases under these defined
contracts. Its pre-existing signed-pointer warning is explicitly suppressed
only when compiling the void baseline helper; the candidate is compiled with
`-Werror` and no pointer-sign suppression. All candidate cases pass. Independent
mutations must be rejected for swallowing the power-on error, splitting the
RMW lock or abandoning the pending off acknowledgement. Tests do not read
physical mailbox registers or establish thermal, DDR-frequency or power behavior.

## Still unproven

This fixes an actual transport/error-path defect; it is **not** a complete failed
reset/DMA quarantine design, an SP quiescence proof, an S0I3 fix or Android parity.
Normal final-frame/CSS/sensor sequencing is untouched. Host checks cannot prove
that hardware stops accessing CSS/VB2 buffers after a failed power fence.
No tablet install, reboot, suspend or physical fault injection was performed.
