# r5 recording: selected H.264 VME execution path

## CONT30: measured MBEnc IDRT hotspot; candidate NOT deployed

Two more10-second requested, full-quality visible-foreground diagnostics ended
normally, with restored controls and no kernel faults. Both still fail cadence:

| Hooks | Frames | fps | MP4 span (s) | Maximum gap | Gaps >50 ms |
|---|---:|---:|---:|---:|---:|
| Run subgroups, ABI3 |404|29.480614|13.670000|76.000 ms|6|
| MBEnc subgroups, ABI4 |417|29.156835|14.267667|81.667 ms|12|

All18/26 respective phase counts match404/417 successful encoder calls;
one load each, zero remaining mappings, reserved histogram unused. Clips decode
fully with no exact adjacent repeats. These windows are diagnostics, not full
30-second recording, optics or Android-parity qualification. Different hook
levels are not a same-binary A/B performance test; perturbation is not excluded.

ABI3 localized MBEnc to8.348054 s wall versus0.285362 s threadCPU. ABI4 splits it:

| Inclusive ABI4 stage | Calls | Wall total (s) | Thread CPU (s) | Wall max (ms) |
|---|---:|---:|---:|---:|
| `encoder_end` | 417 | 10.908143 | 2.020234 | 81.449 |
| `run_mbenc` | 417 | 8.663066 | 0.331764 | 70.875 |
| `mbenc_context_reset` | 417 | 0.013165 | 0.008664 | 1.406 |
| `mbenc_curbe` | 417 | 0.003952 | 0.001586 | 0.152 |
| `mbenc_const_data` | 417 | 1.466834 | 0.052781 | 37.787 |
| `mbenc_mad_clear` | 417 | 0.004632 | 0.001839 | 0.317 |
| `mbenc_surfaces` | 417 | 0.082465 | 0.067508 | 3.329 |
| `mbenc_idrt` | 417 | 6.921016 | 0.047698 | 58.516 |
| `mbenc_walker_prepare` | 417 | 0.004482 | 0.002115 | 0.316 |
| `mbenc_submit` | 417 | 0.149226 | 0.115814 | 2.877 |

IDRT is about63.4% of whole encoder wall time and79.9% of MBEnc wall time.
Constant-data preparation is another1.466834 s. Elapsed time is not proven GPU
execution or a specific kernel wait: blocking and descheduling remain possible.
Per-stage totals do not identify the cause of each individual MP4 gap.

### Shared BO source contract and offline-only candidate

Pinned source creates CURBE and IDRT views into the same dynamic-state BO.
BRC binds the aligned CURBE region for GPU read/write; later
`gen8_gpe_setup_interface_data` CPU-write-maps that BO to populate disjoint IDRT
bytes. This supports a concrete synchronization lead, not a reason to use
unsynchronized maps, skip BRC or overwrite live CURBE data.

An **unqualified offline candidate**, outside production repositories, prepares
the regular non-FEI MBEnc descriptor before submitting the shared-CURBE BRC
work. A per-frame, exact-context readiness pointer is reset at run entry;
other contexts/FEI/decoupled CURBE retain ordinary descriptor setup. It adds no
forced clock, rate/quality reduction or new unsynchronized BO access.

The two-file candidate builds fully against the pinned fork, with the same one
existing HEVC warning as baseline; it is **not staged or GPU-tested**. A
10,640-case host contract test compiles the real BO-init, descriptor-write and
BO-destroy functions plus the real descriptor struct against guarded fake BOs:
CURBE/IDRT regions disjoint, all descriptor/CURBE bytes identical under the two
modeled write orders, redzones/reference checks pass. Existing unused source
`ctx` parameter warnings are suppressed in that fixture. Simulated busy-map
events are not actual GPU waits, and these layout tests do not qualify the
full BRC/MBEnc callback ordering, FEI/CQP transitions or error paths. Those
tests and guarded same-binary hardware A/B must precede deployment.

### Exact cleanup and independent restoration

Only two superseded r3 own-test clips were deleted: the300-frame direct-video
framerate sample and a441-frame short interrupted rear sample. The latter had
clean cadence/decode but did not complete its requested interval; it is not
relabeled a whole-test pass. Total47,654,321 bytes,2,479 protected hashes and35
alias targets unchanged. The170-second host observation expired while the
original tablet process finished its post-delete hashing; the same completed
private receipt was recovered after that process exited. Deletion was not
reissued. All logs/metadata, r4 references, current failed media, source-thread
baseline, photos and installed kernels remain.

Three ended private test caches and three obsolete private diagnostic DSO copies
were also removed; exact DSO exports remain on the host for restaging. Default
cache and installed system driver were not touched. No raw media/logs exported.

Final independent audit:2,214 installed protected files plus48 payload files and
35 aliases unchanged; both fresh geometry/control/input/format snapshots fully
restored, sensors/ISP suspended, PCM closed, all test units ended, temporary
aggregates gone and private driver unmapped. Global loader environment,
no-lock/no-DPMS/no-auto-suspend settings and guards unchanged. Free space
2,153,644,032 bytes, just above the2 GiB floor; no further capture dispatched.
Peak test temperature76 C and observed CPU limit1.6 GHz, without forcing clocks.
No reboot, nonzero playback or production-driver replacement.

Next: test the actual BRC/MBEnc order and all fallback contexts, then prepare a
private opt-in same-binary A/B build. Reclaim only independently verified
obsolete test data or losslessly archived logs before more recording; retain
current failing samples. Recording performance remains unqualified.

Primary source: [BO layout and descriptor writes](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/i965_gpe_utils.c#L1124-L1188), [BRC CURBE binding and submission](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/i965_avc_encoder.c#L2995-L3185), [MBEnc descriptor setup](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/i965_avc_encoder.c#L5326-L5353). [Whitelisted scalar evidence](tests/mipad2-7.2-r5-mbenc-idrt-summary.json).

## 2026-10-25: corrected backend attribution, NOT a cadence fix

The preceding report proposed measuring the legacy Gen8 H.264 post-pack/BRC
loop. That was a source lead, not proof that this device executed it. Actual
private-driver counters now show **zero calls to that legacy loop**. The
matching IRQL 2.4.5 source delegates Gen8/CherryView H.264 to the Gen9 AVC VME
and PAK backends. A generation label alone was insufficient to select hooks.

### First diagnostic: useful partial counters, failed coverage assertion

A 10-second requested, visible foreground, full-quality capture decoded all
412 frames. Measured 29.339679 fps, MP4 span14.008333 s, max gap77 ms, nine gaps
over50 ms. Generic encoder/VME/MFC counters were valid; all legacy hooks zero.
The controller's expected-legacy-count assertion failed after normal app exit
and control restoration. Its original failed result/log remain preserved.
Only that ended, owned failed unit was reset after recording its failed state;
the reset does not make the diagnostic pass. No blind recapture was issued.

### Corrected diagnostic: selected VME covered, cadence still fails

A distinct private module measures the actual selected pipeline. All eleven
phase counters have405 calls and zero returned errors; producer identity,
single load, zero remaining mappings and unused reserved histogram verified.
Requested10 s; observed MP4 span13.703333 s, 405 decoded frames, **29.481878 fps**,
maximum gap**71 ms**, nine gaps over50 ms. No adjacent decoded frames are exact
duplicates. Both video/audio decode; none of this proves full sensor-to-MP4
frame conservation or Android parity.

| Inclusive phase | Calls | Wall total (s) | Thread CPU (s) | Wall max (ms) |
|---|---:|---:|---:|---:|
| `encoder_end` | 405 | 10.586582 | 1.845102 | 73.930 |
| `vme_pipeline` | 405 | 10.383020 | 1.669434 | 66.767 |
| `avc_vme_allocate_resources` | 405 | 0.558890 | 0.504328 | 13.453 |
| `avc_vme_kernel_prepare` | 405 | 0.018625 | 0.013945 | 1.866 |
| `avc_vme_kernel_run` | 405 | 9.777455 | 1.119891 | 64.328 |
| `mfc_pipeline` | 405 | 0.179157 | 0.151985 | 10.351 |

The run stage contributes about92.4% of total encoder wall time and94.2% of VME
wall time. Resource allocation is about0.559 s of10.587 s total encoder time,
not the leading component in this run. Nested totals must not be added.
Elapsed-minus-thread-CPU time can include blocking or descheduling; it is not
an independently measured GPU-execution/IRQ/firmware defect. Per-stage
aggregates do not prove which particular MP4 gap was caused by which call.

The actual run function includes BRC initialization, scaling, hierarchical ME,
SFD, BRC updates, optional weighted prediction and MBEnc. It contains several
CURBE mappings through nested callbacks; no wait is bypassed and no buffer is
overwritten unsynchronized. Rate control, quality, resolution/bitrate, visible
preview and callbacks are unchanged. These source-built diagnostic binaries
are not claimed to reproduce the installed package byte-for-byte.

### Offline next instrumentation, not a deployed fix

Seven further aggregate groups split those actual run-function stages.
ABI3:18 phases/1,344 bytes, PID-scoped optional mmap, no payload reads or
per-frame file writes. Group counts also include no-op branches. This version
is **built only, not staged or hardware-tested**. The real selected run
function, compiled with stubbed dependencies, gives identical callback order,
arguments, return/errno and weighted-prediction flag effects in baseline,
disabled and enabled builds over8,192 deterministic branch cases and33,272
callback events. Six selected pipeline success/early-error cases also match.
These are host semantic tests, not GPU tests or exhaustive configurations.

The new code/fixtures pass Wall/Wextra/Werror. Full driver builds retain one
pre-existing Gen9 HEVC array-bounds warning, also present in baseline; they
are not described as warning-free. A same-binary enabled/disabled hardware
comparison remains outstanding. Instrumentation perturbation is not excluded.

### Cleanup and restoration

No media was deleted. Only ended, isolated regenerable test caches were
removed under the existing authorization. One prior pad trace was losslessly
gzip-compressed with byte-exact decompression/record-count verification before
removing its raw copy; real Btrfs free-space gain was only about1.83 MB.
The compressed trace remains device-private; old raw-path analyzers require a
gzip-aware replay adapter. Default app/cache, photos, kernels, logs, failed
clips, source-thread baselines, r4 references and35 private alias targets remain.

Independent postflight:2,214 protected installed files plus48 payload files
unchanged;35 aliases unchanged; both fresh geometry/control snapshots restored;
sensors/ISP suspended, PCM closed, temporary aggregates removed, private driver
unmapped, installed driver unchanged and global loader environment clean.
Requested no-lock/no-DPMS/no-auto-suspend settings and guards retained. Free
space2,156,158,976 bytes is only about8.1 MiB above the2 GiB reserve: no further
capture was dispatched. No reboot, production-driver replacement or nonzero
playback occurred. Peak diagnostic temperature79 C; CPU limit observed1.6 GHz,
thermal guard unchanged. This is not pristine thermal-performance qualification.

Only the separately validated codec PLL patch is submitted upstream in
[PR8](https://github.com/xiaomi-latte-dev/linux_latte/pull/8). The unresolved
recording work is not bundled into that stable, narrow codec change.

### Pinned primary sources and scalar evidence

- [Gen8 H264 VME delegation](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/gen8_vme.c#L1343-L1346).
- [Gen8 H264 PAK delegation](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/gen8_mfc.c#L4717-L4720).
- [Actual selected AVC run/pipeline](https://github.com/irql-notlessorequal/intel-vaapi-driver/blob/0b648be50cd80e16469c135c76ff61bbd2f2d12b/src/i965_avc_encoder.c#L8622-L8757).
- [Whitelisted aggregate measurements](tests/mipad2-7.2-r5-selected-vme-summary.json).
- [Preceding encoder/backpressure evidence](MIPAD2_R5_ENCODER_WAIT_7_2.md).
