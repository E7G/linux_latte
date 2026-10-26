# Opt-in Cherryview GPU MBEnc IDRT experiment

Source-only companion to the MiPad2 7.2 integration branch. **Not a kernel
patch, default driver replacement, release binary or Android-parity claim.**
The i965 user-space driver otherwise maps a BRC-owned dynamic-state BO on the
CPU to update its interface descriptor; this can serialize pending GPU work.
This candidate writes the same 32 descriptor bytes through four ordered Gen8
PIPE_CONTROL post-sync qwords, then invalidates the relevant read caches before
the unchanged pipeline/descriptor load. It retains CS_STALL, normal writable
relocations, existing flushes, dependencies, encoder settings and CURBE bytes.

Requires Python 3.9+, `patch`, a C11 compiler with UBSan; optional full build
also needs Meson/Ninja and matching libva/libdrm development packages.

## Public, reproducible base

Reference: [irql-notlessorequal/intel-vaapi-driver@0b648be50cd80e16469c135c76ff61bbd2f2d12b](https://github.com/irql-notlessorequal/intel-vaapi-driver/tree/0b648be50cd80e16469c135c76ff61bbd2f2d12b).
The complete eight-file patch includes the optional aggregate diagnostics and
Meson source-list addition. It does **not** require the earlier private
instrumented baseline. All 1,079 regular files of a fresh public commit archive
matched the cached original source. Archive and affected-file pins are in
`manifest.json`; reference headers are additionally pinned by packet tests.
Do not stack the separate CS-stall patch: this patch already contains it.

```sh
# REFERENCE must be the pinned public source, not another instrumented build.
python3 prepare_source.py --reference-root "$REFERENCE" --output-root "$NEW_SOURCE"
python3 -O prepare_source.py --reference-root "$REFERENCE" --output-root "$OTHER_NEW_SOURCE"
python3 test_prepare_source.py --reference-root "$REFERENCE"
python3 -O test_prepare_source.py --reference-root "$REFERENCE"
python3 test_packets.py --source-root "$NEW_SOURCE" --reference-root "$REFERENCE" --receipt manifest.json
python3 -O test_packets.py --source-root "$NEW_SOURCE" --reference-root "$REFERENCE" --receipt manifest.json
python3 -m unittest -v test_snapshot
python3 -O -m unittest -v test_snapshot

# Optional private build, NO install command:
CC=cc CFLAGS='-O2 -g -march=x86-64 -mtune=generic' meson setup "$BUILD" "$NEW_SOURCE" --buildtype=debugoptimized --prefix=/usr --libdir=lib -Dwith_wayland_drm=no -Denable_hybrid_codec=false -Denable_tests=false
ninja -C "$BUILD" -j4
```

Source preparation has ten positive/negative tests, including tampered inputs,
existing output preservation, symlink refusal and post-patch hash validation.
Both the source verifier and strict snapshot reader retain checks under `-O`.

## Scope and fail-closed activation

Default is OFF. A valid owner-only, single-link, PID-scoped aggregate file and
`MP2_I965_GPU_MBENC_IDRT=1` must both exist; the actor sets
`MP2_I965_DIAG_PID` to its own PID before driver loading. Use a fresh absolute
`MP2_I965_DIAG_FILE` in a private directory. Do not use a shell parent's PID.
`MP2_I965_EARLY_MBENC_IDRT` must be unset or zero; enabling both experiments is
rejected. Production launchers and installed driver paths are not modified.

Eligibility is intentionally limited to CHV non-FEI regular MBEnc with BRC
CURBE updates, one 64-byte IDRT slot, no sampler entries and one bounded shared
dynamic-state/CURBE/IDRT BO. Other layouts retain the ordinary CPU path.
Per-context pending state is consumed once inside the existing atomic batch.
An experiment qualification rejects any reported fallback.

`snapshot.py` checks exact ABI6 size/magic/PID/mode, terminal active=0,
all 26 regular phase counts against the **actual** positive packet count,
preparations/uploads/fallback conservation and EARLY exclusion. Counters prove
command-path coverage, not GPU completion, sensor payload identity or cadence.

## Evidence and remaining work

* Extracted real functions: 4,096 randomized descriptor/packet cases per normal,
  NDEBUG and UBSan run; 22 invalid-layout cases. The old boolean CS-stall mask is
  a required failing negative control; CPU descriptor implementation unchanged.
* Actual owned-BO helper: 16 successful render submissions and bounded blocking
  waits; all 4 KiB matched the CPU reference, with all bytes outside the target
  32 bytes untouched. No camera/codec or foreign handles in this test.
* Same instrumented driver, normal camera UI, native 1920x1080 NV12,
  requested H.264 15 Mbps + 48 kHz stereo AAC 192 kbps, requested 30 seconds:
  front OFF 935 decoded packets, 28.856 fps, 18 gaps >50 ms;
  front ON 987, 29.992 fps, zero gaps >50 ms;
  rear ON 970, 30.011 fps, zero gaps >50 ms. Actual input was checked before
  and after rear recording. All ON packets had uploads and zero fallback.
  These are single ordered clips with uncontrolled optical scenes, not a
  counterbalanced performance study or full source-to-MP4 payload proof.
* Separate deterministic **static checkers** input, 180 frames each, native
  1080p/30 NV12, same driver/encoder settings, video only: OFF/ON decoded frame
  hash sequences and extracted H.264 NAL streams were identical. This does not
  cover moving scenes, optical quality, camera exposure, audio or endurance.
* Original failed wrapper diagnostics were preserved: an OFF sample completed
  encoding but a cross-subvolume rename failed. The original completed sample
  was reused, not rerun; only the missing ON cell was executed. A normal
  `debug:` boot line was separately corrected as a diagnostic false positive,
  without overwriting the original receipt or hiding a hardware fault.

Remaining: counterbalanced repeats, moving-input quality, post-camera suspend
and record, long recordings, thermal/battery/power behavior and broad OEM
comparison. Ordinary CPU constant-data upload waits can remain or move later;
do not infer that every encoder latency is fixed from the cadence results.
Private recordings, maps, logs and traces are excluded from this source package.

A fresh public-source patched build passed Meson/Ninja, VA init ABI 1_24 and
`ldd -r`; all 1,081 resulting source files matched the hardware-tested candidate.
One pre-existing HEVC array-bounds compiler warning remains; this is not a
warning-free build or a new hardware qualification of the rebuilt binary.

## Optional hardware byteproof

`owned_BO_byteproof.c` is MIT-licensed and needs the matching patched full
driver headers, VA/libdrm development headers and its private DSO. It verifies
Cherryview/i915 before allocating its own BOs. The GPU submission and 5-second
completion wait are checked, followed by ordinary synchronized CPU readback.
It neither installs a driver nor changes cache policy. No hardware test is run
by the Python offline tests or source preparation commands.
