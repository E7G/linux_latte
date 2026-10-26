# Gen8 PIPE_CONTROL CS-stall mask regression

Source-only fix for `irql-notlessorequal/intel-vaapi-driver` commit
`0b648be50cd80e16469c135c76ff61bbd2f2d12b` (tag 2.4.5).
Reference: https://github.com/irql-notlessorequal/intel-vaapi-driver/tree/0b648be50cd80e16469c135c76ff61bbd2f2d12b

`gen8_gpe_pipe_control()` ORs `!disable_cs_stall` directly into DWORD 1.
A true C boolean sets bit 0 (DEPTH_CACHE_FLUSH), not bit 20 (CS_STALL).
Use `CMD_PIPE_CONTROL_CS_STALL` when requested; keep explicit disable and
all requested cache-invalidation, post-sync, address and relocation fields.
This patch does not bypass synchronization or change encoder quality.

The regression verifies full SHA256 pins of the three reference source files
before applying the zero-context patch to a temporary copy, with fuzz disabled.
It extracts the actual function, parameter struct and packet macros instead of
testing a hand-reimplemented production function. Requirements: Python 3,
`patch`, C11 compiler with UBSan. No GPU, device, root or installation required.

```sh
python3 test_gen8_cs_stall.py --source-root /path/to/intel-vaapi-driver
python3 -O test_gen8_cs_stall.py --source-root /path/to/intel-vaapi-driver
```

Six tests cover 6,144 parameter combinations for each normal, NDEBUG and
UBSan packet run: zero/nonzero disable, all defined flush modes, optional BO,
random payload and 64-bit relocation carry. The original function must fail
the expected-bit negative control. All other words and relocation domains must
remain identical. Python checks remain active under `-O`, C checks under NDEBUG.
The extracted C harness retains the reference source's MIT notice.

A complete private driver build also passed its link/ABI checks. This is an
independent source correctness fix, **not a measured recording-cadence fix**.
No installed driver or kernel is changed by these files. Hardware qualification
and Android-parity recording remain separate, unfinished work.
