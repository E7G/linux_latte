# Mi Pad 2 Linux 6.14 r8: stream-parameter candidate

Source: `1693101f22d18d1844ad32b0ad835ef49bd7732f`.
Release: `6.14.0-mipad2-integrated-r8`.

## Implemented

- AtomISP G/S_PARM clears reserved/unused output fields and never exposes
  internal run-mode enum values as standard capture flags.
- Legacy CI_MODE_VIDEO/STILL_CAPTURE/PREVIEW S_PARM requests remain accepted;
  their response is normalized to the standard stream-parameter structure.
  Standard unsupported capture flags are returned cleared without changing
  the private ISP run mode. No V4L2_MODE_HIGHQUALITY implementation is claimed.
- OV5693 and T4KA3 set_frame_interval converts a requested rational period
  to sensor VBLANK using the existing control callback. It clamps to actual
  control limits without changing the image format. Zero numerator or
  denominator restores the format's default VBLANK.
- Getters return the reduced rational period from actual line timing, not
  a rounded integer FPS. The 64-bit division handles extreme u32 requests.

## Offline evidence (2026-10-10)

- Full LLVM21/ThinLTO W=1 bzImage + modules build passed, exit 0.
- Only CONFIG_LOCALVERSION differs from the validated r7 build configuration.
- r7 .config, bzImage, vmlinux, Module.symvers and System.map hashes unchanged.
- Source files and HEAD unchanged during the complete build.
- Actual sensor pad-op code passed 160120 host-model cases with ASan/UBSan.
- Actual AtomISP G/S_PARM functions passed 47 host-model cases with ASan/UBSan;
  CI_MODE/run-mode constants are extracted from the real kernel header.
- The on-device C regression compiles with -Wall -Wextra -Werror. It has NOT
  run on the tablet. It verifies the selected input matches the sensor subdev
  and attempts all restorations, then reads controls back.
- Existing unrelated kernel/compiler warnings remain; not a warning-free build.

Host tests stub sensor controls, locking and subdevices. They do not prove
register programming, runtime PM, frame cadence or ISP streaming correctness.

## Outstanding device gates

Do not promote this candidate or reboot while a user-assisted camera test is
pending. Keep the saved stable bqdiag1 default and the r7 package unchanged.

After anti-idle/SSH/USB console checks and a protected one-shot setup:

1. Both inputs: G/S_PARM reserved fields, actual rational timing, unsupported
   standard flags, legacy modes, unchanged format, successful control restore.
2. Capture at two frame periods and measure real buffer timestamp cadence.
3. Manual exposure preservation/range behavior with changed VBLANK.
4. Full v4l2-compliance, dual-camera smoke and RTC suspend/resume.
5. Snapshot reopen/front-back switching and user brightness confirmation.

The last measured compliance result is still r7's 64/72, not a prediction for
r8. Multiple-open lifecycle/queue ownership and tiny-format scaling remain
unfixed. Automatic exposure and white balance/3A also remain separate work.

The independently patched Snapshot fixed preset (320/8) is only a temporary
application workaround, not an auto-exposure implementation.
