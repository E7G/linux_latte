#!/usr/bin/env bash
# Build the three tested Mi Pad 2 audio modules for one prepared kernel tree.
set -Eeuo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 KERNEL_SOURCE KERNEL_OUTPUT" >&2
    exit 64
fi
src=$(readlink -f "$1")
out=$(readlink -f "$2")
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test -s "$out/Module.symvers" || { echo "Kernel output lacks Module.symvers" >&2; exit 1; }
test -s "$out/include/generated/autoconf.h" || { echo "Kernel output is not configured" >&2; exit 1; }

build=$(mktemp -d)
trap 'rm -rf -- "$build"' EXIT
mkdir -p "$build/tfa" "$build/rt5659" "$build/machine/sound/soc/intel/boards"
cp -a "$here/src/tfa/." "$build/tfa/"
cp "$here/src/rt5659/rt5659.c" "$build/rt5659/"
cp "$here/src/machine/cht_bsw_rt5659.c" "$build/machine/sound/soc/intel/boards/"
for header in rl6231.h rt5659.h; do
    cp "$src/sound/soc/codecs/$header" "$build/rt5659/"
    mkdir -p "$build/machine/sound/soc/codecs"
    cp "$src/sound/soc/codecs/$header" "$build/machine/sound/soc/codecs/"
done
for header in sound/soc/intel/atom/sst-atom-controls.h sound/soc/intel/common/soc-intel-quirks.h; do
    mkdir -p "$build/machine/$(dirname "$header")"
    cp "$src/$header" "$build/machine/$header"
done

cat > "$build/rt5659/Makefile" <<'EOF'
obj-m += snd-soc-rt5659.o
snd-soc-rt5659-objs := rt5659.o
EOF
cat > "$build/machine/sound/soc/intel/boards/Makefile" <<'EOF'
obj-m += snd-soc-sst-cht-bsw-rt5659.o
snd-soc-sst-cht-bsw-rt5659-objs := cht_bsw_rt5659.o
EOF

make -C "$src" O="$out" M="$build/tfa" modules
make -C "$src" O="$out" M="$build/rt5659" \
    KBUILD_EXTRA_SYMBOLS="$build/tfa/Module.symvers" modules
make -C "$src" O="$out" M="$build/machine/sound/soc/intel/boards" \
    KBUILD_EXTRA_SYMBOLS="$build/tfa/Module.symvers $build/rt5659/Module.symvers" modules

release=$(modinfo -F vermagic "$build/tfa/snd-soc-tfa98xx.ko")
release=${release%% *}
dest="$here/dist/$release"
mkdir -p "$dest"
cp "$build/tfa/snd-soc-tfa98xx.ko" "$dest/"
cp "$build/rt5659/snd-soc-rt5659.ko" "$dest/"
cp "$build/machine/sound/soc/intel/boards/snd-soc-sst-cht-bsw-rt5659.ko" "$dest/"
printf '%s\n' "$release" > "$dest/kernel-release"
cp "$here/hotload.sh" "$dest/hotload.sh"
chmod 755 "$dest/hotload.sh"
for module in "$dest"/*.ko; do
    vermagic=$(modinfo -F vermagic "$module")
    [[ "$vermagic" == "$release "* ]] || { echo "vermagic mismatch: $module: $vermagic" >&2; exit 1; }
done
(cd "$dest" && sha256sum ./*.ko > SHA256SUMS)
echo "Built $dest"
