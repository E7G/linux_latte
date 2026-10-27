# AtomISP PSYS event bounds and explicit protocol-error recovery

The CSS event decoder receives an 8-bit firmware event type. Its conversion table
has 16 valid entries and one zero-valued sentinel. Before this change, both the
first event and the second half of a TIMER event indexed that table without a
bounds check. Event values 17–255 could read beyond it; value 16 selected a sentinel
instead of a valid host event.

The local validator checks the array bound before reading it and rejects the zero
sentinel. Invalid events return `-EPROTO`. The ISR logs the protocol error and
queues its existing assertion-recovery work instead of silently treating the queue
as empty. It does not publish an invalid event as a valid completed frame.

Valid payloads, queue acknowledgments, TIMER pairing/fallback, buffer timestamps,
flags, recovery implementation, firmware, and capture/encoding quality are unchanged.
In particular, a valid `FW_ASSERT` event containing module 255 / line 291 remains
an assertion and retains the existing recovery path. This patch does **not** prove
the cause of the observed firmware assertion or camera stalls.

## Host-side regression

Requirements: Python 3, Clang, AddressSanitizer and UndefinedBehaviorSanitizer runtimes.
Run from the source tree, using a fresh output directory:

```sh
python3 fix_file/tests/test_mipad2_psys_event_bounds.py \
  --output "$(mktemp -d)/run"
python3 -O fix_file/tests/test_mipad2_psys_event_bounds.py \
  --output "$(mktemp -d)/run"
python3 fix_file/tests/mipad2_capture_fault_gate.py
```

The test extracts the real raw event decoder, mapping table, dequeue function,
public event structures/enums, validator and ISR function. Queue transport,
logging, pipe/device state and buffer delivery are stubbed. No device is opened.
An in-memory rollback removes only this patch to make a vulnerable control; an
optional `--baseline-ref` verifies that rollback against a local Git commit, with
lazy fetching disabled. Sources and existing evidence are never overwritten.

Coverage includes all 240 invalid u8 event values at each lookup, 128 sampled
valid payload/TIMER equivalence cases, all 65,536 assertion line numbers for each
of modules 0 and 255, and 544 ISR/recovery cases. Both vulnerable lookup controls
must reproduce an ASan/UBSan out-of-bounds report. The capture fault gate also
rejects new invalid-PSYS diagnostics, even if a resulting video is decodable.

The actual patched `sh_css.c` and `atomisp_compat_css20.c` translation units also
compile with the configured kernel flags and `-Werror`. These results are not a
full module/kernel build, boot, hardware/endurance test, firmware ABI proof, or
Android/Windows feature-parity qualification. Do not promote a kernel on this
host fixture alone.
