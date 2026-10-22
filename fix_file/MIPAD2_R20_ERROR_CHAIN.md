# R20 error-chain research candidate: NOT deployed or fully fault-safe

Running device remains R19 built8c57f2be2, stablebqdiag1 default unchanged.
No physical camera/ISP/PCI fault injected and no R20 boot/stage is authorized
by a passing hostmock alone. This source is an incremental candidate, not
completion of error-lifecycle/DMA safety or the full Linux port objective.

## Reproduced error-return losses

Exact original callback hostprobe: reset/create/CSSstart/sensorstart failures
continued into invalid stages, no queueerror/fatalnotification; successpasses.
Exact power/transport probe104cases:50fail on oldsource,0fail afterchanges.
PCIhelpers return positivePCIBIOS status too; IOSF ignored it by checking<0.
The actualkernel pcibios_err_to_errno converter is extracted into thefixture.
IUNIT powerpoll ignored IOSF request/read errors; atomisp_reset overwrote
failedpoweroff with a later poweron result, falsely reporting reset success.

## Candidate changes

- IOSF PCI mailbox read/write helpers reject any nonzero status and return
  its normalizederrno, stopping at the failedtransaction. Existing success
  and negativeerrno behavior preserved. This sharedIOSF change needs whole
  device/PM regression, not only camera tests.
- IUNIT powerrequest/status errors propagate before status/trace promotion.
  Reset preserves first powerofffailure, marksfatal, does not poweron after
  failedpoweroff. DDRDVFS workaround timing remains unchanged on success.
- Normalstop checks reset/recreate results; no recreate after resetfailure,
  fatalquarantine persists to nextstream instead of warning-only success.
- Async recovery stops at reset/create/CSSstart/sensorstart failure, clears
  ASDstreaming, marksfatal and wakes VB2owner with queue_error. No second
  MCpipeline stop or premature old-frameflush on reset/create/CSSstart errors.
  No extraMMIO after a resetfailure with unknown/offpower state. ANN CSI-ready
  setup matches initialSTREAMON and is disabled after sensor-startfailure.
- Recovery skips an owner already stopping. ThreadedIRQ rechecks streaming
  after ISPmutex acquisition. Stop/failedstart cancel stale work OUTSIDE
  ISPmutex while VB2queuelock still excludes newSTREAMON; fatalqueue avoids
  waiting for IRQ-drain which cannot complete. Source mocks do not establish
  actual scheduler/cancel ordering under every race.
- Failed last-suspend retainsfatal. Quarantined first-open must pass a checked
  reset before clearingfatal; PMget success alone cannot clearit. Failedreset
  balances PM/fh without initialization. CSSuninit is idempotent because
  failedpoweroff may be retried without a matchingCSSinit.

## Bounded verification

23 exact-source hostsuites pass:19 retained camera/buffer/multiopen/control/
geometry/start-stop cases plus4 new transport/recovery/stopIRQ/CSSuninit
fixtures. New tables:104transport/power/reset,40recovery active/idle/stopping
legacy/ANN/error branches,36normalstop/IRQ lock-wait interleavings,8uninit
retry/reinit cases. Existing multiopen fixture retains queue-owner takeover,
2000 closurecycles and16000 concurrentopens/closes; adds quarantine/reset/PM
refbalance and lastsuspendfailure. Old start/unwind28cases retained. Every
fixture uses explicit PM/CSS/PCI/hardware stubs; not physicalfault proof.

## Critical unfinished audit, before any R20 deployment

ia_css_stop_sp currently logs SP/ISP idle timeouts but still returns0 and
frees HMM/parameter bookkeeping. atomisp_css_stop_internal discards thatret
and stream/pipe destructionerrors. Normalstop returns VB2frames BEFORE its
checked powercycle. Therefore hostgreens cannot prove DMAquiescence; normal
stop/release after a failed recovery/powertransition remains a critical gap.
Review softwareCSScleanup versus actualPUNITpower state and retries: unknown
or partlyoffhardware must not receive unsafeMMIO; partial-init/uninit and
retained parameter pointers under in_reset also need a real lifetimeaudit.
The worker deliberately retains frame/MCownership on pre-restart errors, but
its ordinaryownerstop path is NOT thereby proven safe. Do not merely fence
flags, fake idle, assume PCIbusmaster-clear drains outstanding traffic, or
weaken the failed-state tests to claim full completion.

Next isolated LLVM21ThinLTO/W=1 build is a compile/artifact gate only. Preserve
R19 O=artifacts, private signing material, all userdirtyfiles, currentboot,
USBserial/noidle and defaults. No image/credential transfer or tones.
