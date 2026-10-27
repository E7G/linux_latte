# AtomISP raw CSS timing and capture-error qualification

The additive `atomisp_css_frame_timing` event records the exact output buffer's
minor, index, CSS type, exposure/config IDs and raw EOF/start/end ticks, before
the existing completion event under the same queue lock. Only OUTPUT_FRAME and
VF_OUTPUT_FRAME have the EOF field populated by the CSS API. The event exposes
no frame address or pixels and does not change capture timestamps, flags,
formats, buffering, cache policy, scheduling or userspace ABI.

These 32-bit counters are not nanoseconds. Establish the timer domain, rate,
wrap and stream/reset epochs before conversion. An ISP nominal frequency alone
does not prove the timer frequency. Exposure ID zero must not be used as a
unique identity. Recovery error buffers are not fresh CSS frames.

`mipad2_capture_fault_gate.py` adds a strict, append-only kernel-log and source
error check. New FW_ASSERT, GPU/kernel/ISP faults, corrupt source frames or lost
log history fail the gate. A decodable H.264 file is not sufficient evidence of
a valid capture. This gate does not replace optical, cadence, timing identity,
suspend, endurance or uninstrumented validation. It is not a firmware-assert fix.

Run source regressions without hardware:

```
python3 fix_file/tests/test_atomisp_css_frame_timing.py
python3 -O fix_file/tests/test_atomisp_css_frame_timing.py
python3 fix_file/tests/mipad2_capture_fault_gate.py
```

For actual capture qualification, invoke the gate with `--before`, `--after`
and the independently measured `--source-error-frames`. Exit 1 means rejection.
Do not discard, retime or synthesize frames to manufacture a passing result.
Full kernel/module builds and device validation remain separate requirements.

References: [V4L2 timestamps](https://docs.kernel.org/userspace-api/media/v4l/buffer.html),
[event tracing](https://docs.kernel.org/trace/events.html).
