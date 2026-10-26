# AtomISP HMM flush-only mapping regression

`hmm_flush(virt, bytes)` deliberately calls `load_and_flush(virt, NULL, bytes)`.
The per-page kmap path already treats this as flush-only. Both existing-vmap and
new temporary-vmap paths instead unconditionally copied to `data`, dereferencing
NULL for a nonempty flush. Guard the two copies, keeping all existing cache
flush operations, mapping lifetimes, buffer checks and normal load copies.

This is a latent helper API fix, not a claimed explanation for recording jitter.
The current capture QBUF still uses the original `wbinvd()` path. No capture flag,
cache-coherency operation, quality, timestamp or default route is relaxed.

Run the host contract regression from the kernel tree:

```sh
python3 fix_file/tests/test_atomisp_hmm_flush.py -v
python3 -O fix_file/tests/test_atomisp_hmm_flush.py -v
```

The harness extracts the actual four production function bodies; it does not
rewrite their control flow. Synthetic stubs cover uncached existing vmap, cached
existing vmap, successful new vmap, failed vmap/kmap fallback, normal loads,
flush-only calls, zero lengths, invalid buffer lookup and buffer-check failures.
It checks exact synthetic data, unchanged source bytes, copy counts, flush
addresses/total byte counts and balanced mappings. All 19 fixed scenarios pass;
removing only the two guards reproduces rejection of the original three nonempty
vmap flush paths. The original kmap and load paths remain successful.

This does not execute real cache instructions, prove hardware DMA coherence, or
qualify a complete kernel build/boot. It must not be cited as physical camera
frame-conservation or Android/Windows-parity evidence.
