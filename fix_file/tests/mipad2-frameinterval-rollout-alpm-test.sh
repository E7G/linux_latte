#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
stock=$(realpath -- "${1:?verified Arch gst-plugins-good 1.28.7-1 archive required}")
candidate=$(realpath -- "${2:?locally built Mi Pad 2 gst-plugins-good 1.28.7-1.1 archive required}")
test "$(id -u)" = 0
printf '%s  %s\n' bb030193e56f2717d9d735bad19685be1ea22b246f479639c02b52058749a6cf "$stock" |
    sha256sum -c -
pkg_good=5308f10fb81a0d3fbb74f91cd5dc374edec146340e6c18b3afcef3313a883627
pkg_stock=ab342ffb0c018b0d0211d5f9921b3a3f16dde71ca787ea8d6e942e45fc7a3bb3
tmp=$(mktemp -d /tmp/mipad2-gst-alpm.XXXXXXXX)
root=$tmp/root
case "$tmp" in /tmp/mipad2-gst-alpm.????????) ;; *) exit 2 ;; esac
trap 'rm -rf -- "$tmp"' EXIT
config=$tmp/pacman.conf
printf 'Isolated ALPM root: %s\n' "$root"
mkdir -p "$tmp"/{hooks,stock,candidate} "$root"/{etc,usr/bin,usr/lib,var/lib/pacman,run,dev}
ln -s usr/bin "$root/bin"
ln -s usr/lib "$root/lib"
ln -s usr/lib "$root/lib64"
ln -s bin "$root/usr/sbin"
mknod -m 0666 "$root/dev/null" c 1 3
printf '[options]\nArchitecture = x86_64\nSigLevel = Never\n' > "$root/etc/pacman.conf"
printf '[options]\nArchitecture = x86_64\nSigLevel = Never\nHookDir = %s\n' "$tmp/hooks" > "$config"
for name in bash cat mkdir flock sha256sum pacman; do
    binary=$(command -v "$name")
    cp -L "$binary" "$root/usr/bin/$name"
    while read -r library; do
        destination="$root$library"
        if [[ ! -e "$destination" ]]; then
            mkdir -p "$(dirname "$destination")"
            cp -L "$library" "$destination"
        fi
    done < <(ldd "$binary" | awk '$3 ~ /^\// { print $3 } $1 ~ /^\// { print $1 }')
done
ln -s bash "$root/usr/bin/sh"
bsdtar -xf "$stock" -C "$tmp/stock"
bsdtar -xf "$candidate" -C "$tmp/candidate"
python - "$tmp" <<'PY'
import hashlib, pathlib, stat, sys
base = pathlib.Path(sys.argv[1])
def snapshot(tree):
    entries = {}
    for p in (tree / "usr").rglob("*"):
        if p.is_symlink():
            value = ("link", p.readlink())
        elif p.is_file():
            value = (stat.S_IMODE(p.stat().st_mode), hashlib.file_digest(p.open("rb"), "sha256").hexdigest())
        else:
            continue
        entries[p.relative_to(tree).as_posix()] = value
    return entries
stock, candidate = map(snapshot, (base / "stock", base / "candidate"))
plugin = "usr/lib/gstreamer-1.0/libgstvideo4linux2.so"
stem = "mipad2-atomisp-frameintervals"
assert set(stock) <= set(candidate)
assert {p for p in stock if stock[p] != candidate[p]} == {plugin}
assert set(candidate) - set(stock) == {
    f"usr/libexec/{stem}",
    f"usr/lib/systemd/system/{stem}.service",
    f"usr/lib/systemd/system/multi-user.target.wants/{stem}.service",
    f"usr/share/libalpm/hooks/00-{stem}.hook",
    "usr/share/gst-plugins-good-mipad2/v4l2-plugin.sha256",
}
def fields(tree, k):
    return {s[len(k) + 3:] for s in (tree / ".PKGINFO").read_text().splitlines()
            if s.startswith(k + " = ")}
ori, nxt = base / "stock", base / "candidate"
assert fields(nxt, "depend") - fields(ori, "depend") == {"coreutils", "systemd", "pacman", "util-linux"}
assert fields(ori, "depend") <= fields(nxt, "depend")
assert fields(ori, "optdepend") == fields(nxt, "optdepend")
assert fields(nxt, "pkgname") == {"gst-plugins-good"} and fields(nxt, "pkgver") == {"1.28.7-1.1"}
print(f"Payload check: {len(stock)-1} unchanged stock files; replaced one plugin, added five rollout files")
PY

fixture()
{
    local pkg=$1 ver=$2 path="$tmp/fixture-$1-$2"
    mkdir "$path"
    printf 'pkgname = %s\npkgver = %s\npkgdesc = ALPM test fixture\nsize = 0\narch = x86_64\n' \
        "$pkg" "$ver" > "$path/.PKGINFO"
    bsdtar --zstd -cf "$path.pkg.tar.zst" -C "$path" .PKGINFO
}
alpm()
{
    pacman --config "$config" --root "$root" --noconfirm "$@"
}
param="$root/sys/module/atomisp/parameters/stepwise_frame_intervals"
product="$root/sys/class/dmi/id/product_name"
state="$root/run/mipad2-atomisp-frameintervals"
plugin="$root/usr/lib/gstreamer-1.0/libgstvideo4linux2.so"
mkdir -p "$(dirname "$param")" "$(dirname "$product")"
printf 'Mipad2\n' > "$product"
printf 'N\n' > "$param"
fixture gstreamer 1.28.7-1
fixture gst-plugins-base-libs 1.28.7-1
alpm -Udd "$tmp/fixture-gstreamer-1.28.7-1.pkg.tar.zst" \
    "$tmp/fixture-gst-plugins-base-libs-1.28.7-1.pkg.tar.zst"
alpm -Udd "$candidate"
alpm -Qkk gst-plugins-good
test "$(cat "$param")" = N
printf '%s  %s\n' "$pkg_good" "$plugin" | sha256sum -c -
chroot "$root" /usr/libexec/mipad2-atomisp-frameintervals enable
test "$(cat "$param")" = Y
echo 'Correctly paired package enables after boot'

# A parameter write failure must abort the actual ALPM transaction.
mv -- "$param" "$param.saved"
mkdir "$param"
if alpm -Udd "$stock"; then
    echo 'Expected pre-transaction failure' >&2
    exit 1
fi
test "$(alpm -Q gst-plugins-good)" = 'gst-plugins-good 1.28.7-1.1'
printf '%s  %s\n' "$pkg_good" "$plugin" | sha256sum -c -
rmdir "$param"
mv -- "$param.saved" "$param"

alpm -Udd "$stock"
test "$(alpm -Q gst-plugins-good)" = 'gst-plugins-good 1.28.7-1'
test "$(cat "$param")" = N
test -f "$state/inhibit"
test ! -e "$root/usr/libexec/mipad2-atomisp-frameintervals"
printf '%s  %s\n' "$pkg_stock" "$plugin" | sha256sum -c -
alpm -Qkk gst-plugins-good
echo 'Stock rollback restored bytes and disarmed before replacement'

alpm -Udd "$candidate"
chroot "$root" /usr/libexec/mipad2-atomisp-frameintervals enable
test "$(cat "$param")" = N
rm -- "$state/inhibit"
chroot "$root" /usr/libexec/mipad2-atomisp-frameintervals enable
test "$(cat "$param")" = Y
fixture gstreamer 1.28.8-1
alpm -Udd "$tmp/fixture-gstreamer-1.28.8-1.pkg.tar.zst"
test "$(cat "$param")" = N && test -f "$state/inhibit"
rm -- "$state/inhibit"
chroot "$root" /usr/libexec/mipad2-atomisp-frameintervals enable
test "$(cat "$param")" = N
echo 'PASS: real ALPM install, pre-transaction abort, stock rollback, same-boot inhibit and incompatible runtime update'
