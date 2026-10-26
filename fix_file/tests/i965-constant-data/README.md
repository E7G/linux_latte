# i965 FTQ threshold unsigned shifts

This is a **user-space dependency** fix, not a kernel/AtomISP cache policy change.
It is retained here because the MiPad2 recording stack uses this driver.

Reference: [irql Intel VA-API 2.4.5 source](https://github.com/irql-notlessorequal/intel-vaapi-driver/tree/0b648be50cd80e16469c135c76ff61bbd2f2d12b),
`src/i965_avc_encoder.c`, reference SHA256 `ad43b90c33505293386f53ff7f5ec44eee28c6e1392915a6b0583bf6354e4f82`.
The Intel-derived source retains its existing MIT license.

## Reproduced defect and exact scope

In `gen9_avc_load_mb_brc_const_data`, an enabled custom FTQ threshold byte
promotes from `uint8_t` to signed `int` before `<< 24`. Bytes 128 through 255
produce signed-shift undefined behavior on the tested compiler/target.
Cast operands to `uint32_t` **before** shifting; casting the result is too late.
The patch changes only five shift operand promotions, keeping the intended
packed bit pattern, table values, enable conditions, QP layout, quality controls,
ordinary synchronized map/unmap, driver resource lifetimes and cache flushing.

This does **not** prove the optional custom-FTQ path was active in ordinary
MiPad2 recordings, or that undefined behavior caused the measured 27–28 fps
cadence failure. It is not presented as the recording performance fix.
The separate experimental constant-input reuse candidate is NOT included or
enabled by these files. Neither installed driver nor desktop defaults change.

## Reproduce without a GPU or installing a driver

Fetch/check out the exact reference commit in a separate directory, then run:

```sh
python3 test_ftq_unsigned.py --reference /absolute/reference/src/i965_avc_encoder.c
python3 -O test_ftq_unsigned.py --reference /absolute/reference/src/i965_avc_encoder.c
```

Requires `cc` (GCC/Clang with UBSan) and `patch`. The test checks the full
reference-file SHA256 and applies the exact patch in an isolated temporary
directory with fuzz disabled. Its zero-context hunks are guarded by the full
reference SHA256 before application. It compiles the **actual extracted source block**,
not a rewritten imitation. All 256 threshold bytes, both enable states, all 52
QP slots, untouched words and two boundary canaries are checked against an
independent unsigned oracle, under normal, `-DNDEBUG`, and UBSan builds.
The real original source and each of the two reverted `<<24` casts must fail
the UBSan negative controls. Python `-O` does not disable validation.

Source/differential qualification is not GPU, decoded-image, dual-camera,
thermal/power, frame-conservation or Android/Windows-parity qualification.
No raw camera images, recordings, traces, machine identifiers or credentials
are included. This is own-repository work; no upstream PR is submitted.
