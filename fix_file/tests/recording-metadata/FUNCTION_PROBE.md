# Optional function-entry/return timing observer

`mipad2_function_probe.py` decodes metadata from a dedicated set of paired
entry/return probe events, using integer monotonic timestamps and exact task/function
stacks. It does not parse function arguments, addresses or image payloads.
`parse(text, prefix)`, `pair(records, profile)`, and `summarize(records, calls)`
are the reusable interfaces. The profile is an event-name mapping to `hits` and
`missed`; a complete caller must independently verify zero ring-buffer loss.

Probe event names use `<prefix>_{qbuf,irq,css_queue}_{begin,end}`. Supply a unique
prefix for each case. The tracefs `kprobe_profile` rows contain the EVENT name,
not the event GROUP name. Register disabled probes, enable only the owned private
instance, keep a bounded ring, and remove only owned probes in a finally block.
Preserve all original global trace settings and definitions. A text append helper
must not issue SEEK_END against tracefs: use native `os.open`/`os.write`, as a
normal shell append does, rather than Python's seek-on-append file wrapper.

See primary interfaces:
- [Kernel kprobe event documentation](https://docs.kernel.org/trace/kprobetrace.html)
- [Kernel event filtering documentation](https://docs.kernel.org/trace/events.html)

## Actual unloaded r6 baseline

The existing native 1080p NV12 lifecycle fixture completed two cameras, four
120-frame phases each: 960 buffers. Six opt-in entry/return probes were active
only in a private monotonic-clock instance, with 2 MiB per CPU bounded storage.
No encoded/saved recording was made. All normal cache/coherency/quality policies
and the native fixture's original battery/temperature/space guards stayed in place.

|Observed function|Calls|Median|p99|Maximum|
|---|---:|---:|---:|---:|
|Native QBUF callback|992|81 us|185 us|392 us|
|Threaded ISP IRQ handler|1920|147 us|272 us|479 us|
|Queue buffers to CSS|1928|42 us|109 us|1869 us|

All 9680 entry/return records paired into 4840 calls, matched the six real probe
profile hit counts, and had zero probe misses or trace-ring loss. Text timestamp
resolution is 1 us; nanosecond units do not imply nanosecond measurement precision.
All 960 native DQBUF identities matched kernel completions. Every DONE event was
observed strictly inside its exact same-task IRQ entry/return scope, without a
nearest-time association. The eight stream-start zero CSS IDs remain opaque.

There were 960 CSS calls nested in QBUF and 960 in IRQ scopes. Eight other CSS
calls are outside those two parent scopes; their durations must not be attributed
to those parents. Subtracting nonoverlapping CSS-child elapsed intervals is not
an isolated measurement of cache flush, mutex wait, off-CPU delay or CPU execution.

This unloaded control does NOT qualify recording cadence, optical latency, DMA
coherence, physical sensor frame conservation, or Android/Windows parity. Loaded
recording cases still have long native-completion intervals and require separate
causal profiling. These numbers do not justify changing the QBUF `wbinvd()` path.

Both sensors and ISP were independently verified restored and runtime-suspended
with usage zero. The private trace instance and all six probe definitions were
removed; original global trace configuration was restored. Raw traces and per-event
metadata remain private on the tablet; only source, synthetic tests and scalar
scope statements belong in this repository. These are own-repository diagnostics,
not material submitted in an upstream PR.
