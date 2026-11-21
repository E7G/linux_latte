# Paired AtomISP frame-interval rollout

This is a downstream Arch derivative of `gst-plugins-good 1.28.7-1`.
It replaces only the V4L2 plugin and adds the Mi Pad 2 rollout controls.
It is not a flash image, an official Arch build, or a replacement for an
unrelated GStreamer version.

## Build inputs

Place the original x86-64 `gst-plugins-good-1.28.7-1` package and the
qualified `libgstvideo4linux2.so` next to `PKGBUILD`. The recipe pins both
hashes. Verify the original package's detached Arch signature and retain
that package for rollback. The companion plugin is built from
`gst-plugins-good 1.28.7`, with both GStreamer patches in `fix_file`,
`v4l2=enabled`, `v4l2-libv4l2=enabled`, and `v4l2-gudev=enabled`.
Build with `makepkg` and use the deployment site's normal package
signing and trust policy; do not relax pacman's configuration.

The original non-V4L2 payload is copied without rebuilding. Keep the
recipe's library digest pinned to a build that passed the paired device
tests. Rebuilding the plugin with a different toolchain or source/build
paths can change its digest; verify it again before updating the pin.

## Activation and rollback

Use a kernel with the default-off `atomisp.stepwise_frame_intervals`
module switch; the unguarded LPAT12 prototype is not a production target.
Install the package while retaining a known-good kernel and the signed
stock userspace package. Do not activate from an already running desktop
session: applications may have cached or loaded the old plugin.

With the sensor modules loaded normally, the packaged systemd unit runs
before graphical login on the next boot. It enables STEPWISE only on a
Mi Pad 2, with the exact qualified native GStreamer packages and matching
V4L2 plugin hash. If the module is absent, the checks fail, or the service
is stopped, the new enumeration stays or falls back to the legacy
`ENOTTY` behavior. No sensor timing or legacy discrete enumeration changes.

The ALPM pre-transaction hook turns STEPWISE off before related package
changes, and prevents same-boot reactivation. If it cannot confirm the
old behavior, the package transaction aborts before replacing files.
For rollback, install the retained official package normally with
`pacman -U`; the hook runs before the derivative and its unit are removed.
A future GStreamer upgrade does not need to retain the old version:
until the new pair is qualified, the camera stays on legacy behavior.
This guard covers the native Arch backend and ALPM-managed changes, not
bundled runtimes such as Flatpaks or unmanaged modifications.

## Acceptance

`fix_file/tests/mipad2-frameinterval-rollout-host-test.sh` exercises the
actual policy with fixture files. The ALPM test takes the verified
original and locally built replacement archives, and uses a disposable
installation root to check payload identity, normal work, abort on
failure, rollback, and a mismatched runtime. This does not replace a
guarded-kernel boot test on the Mi Pad 2.
