# R19 actual one-shot and hardware regression evidence

Built source8c57f2be2c2df6ffb811742478b0a0761bb80563, isolated LLVM21
ThinLTO/W=1 full bzImage/modules success. Prior R18 five build artifacts remain
unchanged. All34 module CMS signatures cryptographically verified, protected
append-only stage/initrd, byte-checked GRUB images and one selected USB verbose
boot succeed. Stable bqdiag1 saved default unchanged; no repeated reboot.

All17 actual hardware test phases finish exit0: silent cold/post-resume audio
electrical paths, held-powered T4 width/HBLANK coherence, both-sensor per-fd
events, guarded geometry, crop extremes, unmodified sensor/video compliance,
strict queues, restart, CREATE_BUFS size/stream contracts, warm modes,
scaling/even-size matrices, long metadata, default/minimum bounds, final RTC.
Geometry has6 x240=1440frames and24 ACTIVE-busy phases; default/minimum39 x240
=9360frames with their period gates all passing. These are bounded fixtures,
not all-format/all-interval/physical maximum-rate or optical quality proofs.
Final post-camera10s RTC resumes and adds9,562,112us S0I3; no tones/acoustic
confirmation. Sampled restorations include mutable controls/test patterns/flips.

Two own harness issues are retained, not recast as kernel failures: the first
batch tried a v1 report basename after a successful v2 powered test; its actual
v2 report was recovered, not rerun. Next event preflight found no staged v2
binary and exited before any probe/control write. Canonical corrected ENOENT
event source was then compiled/pinned, fresh v3 scopes used, both probes pass.
The original logs/state files remain intact outside this sanitized summary.

18 source-extracted host suites plus168 full T4 enable/positive-PM/error-unwind
cases pass with explicit hardware/PM stubs. This is NOT physical bus-error
injection or proof of failed-stop/start/reset recovery on the device. New
portable T4 fixture reproduces those168 cases, no workspace output dependency.

R19 GUI/picture/recording validation is still pending. R18's separate diagnostic
r13c four actual10s recording cycles are30fps with no>100ms packet gaps, four
video/audio software null decodes pass, both sensor PM usages0/suspended after
graceful close; RTC adds9,134,656us S0I3. Those are R18 baseline results, not
silently assigned to R19 or equated with GUI/optical Android parity.

Still pending: hardware fault/error transactions; normal-stop reset and async
recovery-worker failure handling; native full-resolution photos/mode changes;
GUI responsiveness, AE/AWB/AF/NR/quality vs Android/Windows; headless boot,
physical high rates/all intervals, compatibility/Requests, OEM DSP and other
hardware, flash-image build/integration. Full objective remains active.

See tests/mipad2-6.14-r19-validation-summary.json and MIPAD2_R19_LIFECYCLE.md.
