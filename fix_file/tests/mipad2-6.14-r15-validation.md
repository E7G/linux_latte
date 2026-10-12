# Mi Pad 2 R15 source candidate — not device validated

Prepared2026-10-12. Tablet remainsR14, stable defaultbqdiag1. NoR15 boot,
DMA/IRQ, streaming-compliance, acoustic or GUI success claimed.

## ABI reconstruction

The pinned Mi Pad2 Android kernel d2afb1de9a761ff01dafdf9efe4736e521ab71f6
encodes exp_id in reserved[31:16], and configID in reserved2. Linux6.14's
wrapper instead writes raw exp_id into the request_fd union alias, while
standard V4L2 requires valid reserved/request fields. Current upstream still
has that legacy code; it is not an available upstream fix to blindly backport.
Windows reference CPF/AIQB binaries are tuning data, not open3A algorithm
sources. The adjacent pinned Android ABI audit records source hashes/offsets.

- Each capture file handle starts in STANDARD0. DQBUF leaves VB2 fields
  intact; standard QBUF never interprets reserved2 as a private setting.
- Explicit preallocation mode ioctl supports LEGACY1(raw6.14 layout) and
  ANDROID2(shifted original Android layout). These modes deliberately use
  the old nonstandard wire fields, NOT standard compliance. Private per-frame
  settings remain usable in these explicit modes; full MediaRequests support
  remains a separate, unfinished migration.
- New32byte pointer-free FRAME_METADATA ioctl correlates raw exposure/config
  identifiers with the standard DQBUF index/sequence/timeval timestamp_us.
  Cache is per-FH, protected by its own spinlock, and invalidated by successful
  QBUF. The query reads a captured snapshot, not a live buffer or permission
  to access later3A statistics. Mismatched/absent keys returnEAGAIN. Snapshot
  may remain after STREAMOFF/pool release; caller must use the exactDQ tuple
  and query before reuse. Existing compat32 route remains disabled in this
  kernel: fixed-width layout is not a claim of full32bit ioctl support.
- Metadata-mode change refuses allocated queues and uses trylock, because
  default ioctls already holdISPmutex while queue callbacks takequeue→ISP.
  No blocking inverted queue acquisition. Open uses a zeroed extended FH,
  v4l2_fh first so existing generic release can free the complete allocation.
- QBUF rejects nonowners BEFORE shared config mutation; VB2 errors restore
  the prior config ID and retain the previous metadata snapshot. IRQ-visible
  transient nonowner mutations are not justified merely by returningEBUSY.

## Crop arithmetic

OV5693 clamps signed positions/unsigned sizes BEFOREALIGN, leaves minimum
room at the native-array edge, and never produces zero rectangles there.
Direct format huge requests are clamped beforeALIGN too, rather than wrapping
to tiny/binning selections. This fixes arithmetic/empty-crop source defects,
not all streaming-mutation locks or control-error rollback behavior.
No known zero/divide-by-zero path was executed on the tablet.

## Offline gates and required next work

Eleven source-extracted/stub suites pass, including1,506 metadata-policy/
owner/rollback/error cases and5,850 realcrop/format/VTS boundary cases under
ASan/UBSan/Werror. Existing multiopen allocator/owner/PM tests now exercise
the real extended-FH helper, failure cleanup, mode isolation,2,000 closure
cycles and16,000 concurrent opens/closes. Four deliberately regressed metadata
fixtures and the actual oldOVsource compile then fail assertions. Real W=1
driver header preflight passed before style-only cleanup; full pinned rebuild
is still required. Checkpatch has0errors/warnings/checks.

Next: full build/signatures/protected stage/one-shot boot; independent real
standard metadata/DQBUF reserved-field checks; both legacy layouts and typed
keys/error/observer isolation; original3876frame gates and enhanced matrices;
actual streaming compliance without hidinginput0 timeout; crop edge hardware
only after source fix is booted; RTC/electrical audio without tones. R14
default/high-rate timing failures, interval enumeration,3A/AWB/quality, GUI/
recording, broader hardware andflash-tools integration remain open. No
fabricated15/30 interval list or blanket60fps ceiling introduced.

Primary sources:
- https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/buffer.html
- https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_ioctl.c
- https://github.com/torvalds/linux/blob/master/drivers/staging/media/atomisp/pci/atomisp_ioctl.c
