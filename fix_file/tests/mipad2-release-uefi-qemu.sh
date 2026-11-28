#!/usr/bin/env bash
# Isolated UEFI one-shot and fallback validation for two GitHub kernel artifacts.
set -Eeuo pipefail
umask 077
export LC_ALL=C
candidate=$(realpath -- "${1:?candidate artifact directory}")
fallback=$(realpath -- "${2:?fallback artifact directory}")
out=$(realpath -- "${3:?empty output directory}")
expected=${4:?full candidate source SHA}
[[ "$expected" =~ ^[0-9a-f]{40}$ ]]
test -z "$(find "$out" -mindepth 1 -maxdepth 1 -print -quit)"
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
expected_release=7.2.15-mipad2-integrated-release-ci
fallback_release=7.2.15-mipad2-integrated-lpat31
work=$(mktemp -d "$out/work.XXXXXXXX")
trap 'rc=$?; printf "%s\n" "$rc" > "$out/exit-status"; exit "$rc"' EXIT

# Validate exactly the authorized receipt names and the module archive before
# any of its members can become files in the isolated guest.
python3 - "$candidate" "$fallback" "$work" "$expected" "$expected_release" "$fallback_release" <<'PY'
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile

C, F, W = map(pathlib.Path, sys.argv[1:4])
commit, release, fallback_release = sys.argv[4:]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def digest(path):
    require(path.is_file() and not path.is_symlink(), f"unexpected artifact type: {path.name}")
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

expected_names = {
    "bzImage", "config", "module-signing-public.x509", "kernelrelease.txt",
    "module-verification.json", "modules.tar.zst", "source-commit.txt", "pmc-trace-link.txt",
}
seen = set()
for line in (C / "SHA256SUMS").read_text().splitlines():
    m = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
    require(m and m[2] in expected_names and m[2] not in seen, "unexpected release manifest entry")
    require(digest(C / m[2]) == m[1], "release digest mismatch: " + m[2])
    seen.add(m[2])
require(seen == expected_names, "incomplete release manifest")
require((C / "source-commit.txt").read_text().strip() == commit, "wrong candidate SHA")
require((C / "kernelrelease.txt").read_text().strip() == release, "unexpected candidate version")
cfg = set((C / "config").read_text().splitlines())
require({"CONFIG_X86_INTEL_LPSS=y", "CONFIG_EVENT_TRACING=y", "CONFIG_MODULE_SIG=y"} <= cfg,
        "missing diagnostic / signature configuration")

fa = F / "mipad2-72-lpat31.tar.zst"
cs = (F / "mipad2-72-lpat31.tar.zst.sha256").read_text().strip().split()
require(len(cs) == 2 and cs[1] == fa.name and digest(fa) == cs[0], "fallback archive digest mismatch")
fm = json.loads((F / "manifest.json").read_text())
require(fm["source_commit"] == "3f4956789e34da213332510246d565920a23578c" and
        fm["kernelrelease"] == fallback_release and
        fm.get("all_module_signatures_cryptographically_verified") is True, "unqualified fallback")

def open_tar(path, fn):
    with subprocess.Popen(["zstd", "-dc", "--", str(path)], stdout=subprocess.PIPE) as proc:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            fn(archive)
        # tarfile may stop at end markers before the decompressor emits tar padding.
        while proc.stdout.read(65536):
            pass
        require(proc.wait() == 0, "zstd rejected the archive")

image_name = f"var/lib/mipad2-kernel/{fallback_release}/vmlinuz"
def fallback_image(archive):
    count = 0
    for item in archive:
        if item.name.removeprefix("./") != image_name:
            continue
        require(item.isfile() and item.size <= 64 * 1024**2, "unexpected fallback image member")
        with archive.extractfile(item) as src, (W / "lpat31.vmlinuz").open("xb") as dst:
            shutil.copyfileobj(src, dst)
        count += 1
    require(count == 1 and digest(W / "lpat31.vmlinuz") == fm["files_sha256"][image_name],
            "fallback image disagrees with artifact manifest")
open_tar(fa, fallback_image)

prefix = ("lib", "modules", release)
guest = W / "candidate-root"
def modules(archive):
    paths = set()
    total = 0
    for item in archive:
        name = pathlib.PurePosixPath(item.name)
        require(not name.is_absolute() and name.parts[:3] == prefix and ".." not in name.parts
                and item.name not in paths and (item.isdir() or item.isfile()),
                "unsafe or unexpected kernel module archive member")
        target = guest / name
        if item.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            total += item.size
            require(total < 64 * 1024**2, "module archive exceeds expected size")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(item) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
        paths.add(item.name)
    require((guest / "lib/modules" / release / "kernel").is_dir(), "empty module tree")
open_tar(C / "modules.tar.zst", modules)
print("PASS candidate and fallback artifact digests, sources and archive layout")
PY

python3 "$repo/scripts/mipad2_verify_release_modules.py" \
    "$work/candidate-root/lib/modules/$expected_release" \
    "$candidate/module-signing-public.x509" "$expected_release" \
    | tee "$out/module-verification.json"

cd "$work"
base_init() {
    mkdir -p "$1"/{usr/bin,proc,sys,dev}
    # busybox-static is the only guest binary in the fallback image.
    install -m 0755 "$(command -v busybox)" "$1/usr/bin/busybox"
}
base_init candidate-root
base_init fallback-root
kmod=$(command -v kmod)
install -m 0755 "$kmod" candidate-root/usr/bin/kmod
ln -s kmod candidate-root/usr/bin/depmod
ln -s kmod candidate-root/usr/bin/modprobe
ldd "$kmod" > "$out/kmod-libraries.txt"
if grep -Fq 'not found' "$out/kmod-libraries.txt"; then exit 8; fi
mapfile -t libs < <(awk '$2 == "=>" && $3 ~ /^\//{print $3} $1 ~ /^\//{print $1}' "$out/kmod-libraries.txt")
(("${#libs[@]}" > 0))
cp -L --parents -- "${libs[@]}" candidate-root/

cat > candidate-root/init <<'GUEST'
#!/usr/bin/busybox sh
set -eu
bb=/usr/bin/busybox
trap 'rc=$?; echo "QUAL_FAILURE=$rc"; "$bb" poweroff -f' EXIT
"$bb" mount -t proc proc /proc
"$bb" mount -t sysfs sysfs /sys
"$bb" mount -t devtmpfs devtmpfs /dev
trace=/sys/kernel/tracing
"$bb" mount -t tracefs tracefs "$trace"
release=$("$bb" uname -r)
test "$release" = 7.2.15-mipad2-integrated-release-ci
echo "QUAL_CANDIDATE=$release"
event=events/pmc_atom/pmc_atom_s2idle
test "$("$bb" cat "$trace/$event/enable")" = 0
for field in func_dis func_dis_2 d3_sts_0 d3_sts_1 pss forced_clks; do
    "$bb" grep -Eq "field:[^;]*[[:space:]]$field;.*size:4;.*signed:0;" "$trace/$event/format"
done
instance="$trace/instances/mipad2-release-qual"
"$bb" mkdir "$instance"
echo 1 > "$instance/$event/enable"
test "$("$bb" cat "$instance/$event/enable")" = 1
test "$("$bb" cat "$trace/$event/enable")" = 0
echo 0 > "$instance/$event/enable"
"$bb" rmdir "$instance"
echo QUAL_PMC_TRACE_DEFAULT_OFF_AND_ISOLATED=1
test "$("$bb" cat /sys/module/module/parameters/sig_enforce)" = Y
/usr/bin/depmod -a "$release"
for check in intel-chtwc-adc intel_pmic_chtwc_thermal erofs nft_nat nft_masq nft_chain_nat \
             ov5693 t4ka3 atomisp dw9719 snd_soc_rt5659; do
    echo "QUAL_LOADING=$check"
    /usr/bin/modprobe "$check"
    registered=$("$bb" printf '%s' "$check" | "$bb" tr '-' '_')
    "$bb" grep -q "^$registered " /proc/modules
done
echo QUAL_SIGNED_MODULE_LOADS=11
echo QUAL_CANDIDATE_PASS=1
trap - EXIT
exec "$bb" poweroff -f
GUEST

cat > fallback-root/init <<'GUEST'
#!/usr/bin/busybox sh
set -eu
bb=/usr/bin/busybox
trap 'rc=$?; echo "QUAL_FAILURE=$rc"; "$bb" poweroff -f' EXIT
"$bb" mount -t sysfs sysfs /sys
trace=/sys/kernel/tracing
"$bb" mount -t tracefs tracefs "$trace"
release=$("$bb" uname -r)
test "$release" = 7.2.15-mipad2-integrated-lpat31
test -r "$trace/events/power/suspend_resume/format"
test ! -e "$trace/events/pmc_atom/pmc_atom_s2idle/format"
echo "QUAL_FALLBACK=$release"
echo QUAL_FALLBACK_PASS=1
trap - EXIT
exec "$bb" poweroff -f
GUEST

initrd() {
    chmod 0755 "$1/init"
    (cd "$1"; find . -print0 | sort -z | cpio --quiet -o --null -H newc --owner=0:0 | gzip -1) > "$2"
}
initrd candidate-root candidate.initrd
initrd fallback-root lpat31.initrd

cat > "$out/grub.cfg" <<'GRUB'
insmod serial
serial --unit=0 --speed=115200
terminal_input serial
terminal_output serial
insmod part_gpt
insmod fat
insmod search_fs_file
insmod loadenv
search --no-floppy --file --set=root /mipad2-release-fixture
load_env -f /grubenv
set default="${saved_entry}"
if [ -n "${next_entry}" ]; then
    set trial_entry="${next_entry}"
    set next_entry=
    if save_env -f /grubenv next_entry; then
        echo "QUAL_ONE_SHOT_CONSUMED=1"
        set default="${trial_entry}"
    else
        echo "QUAL_GRUBENV_WRITE_FAILED=1"
    fi
fi
set timeout_style=menu
set timeout=0
menuentry 'Mi Pad 2 combined qualification' --id mipad2-ci-once {
    echo "QUAL_GRUB_SELECTED=candidate"
    linux /candidate.vmlinuz console=ttyS0,115200 module.sig_enforce=1 panic=-1 loglevel=5
    initrd /candidate.initrd
}
menuentry 'Mi Pad 2 LPAT31 fallback' --id mipad2-7215-lpat31-once {
    echo "QUAL_GRUB_SELECTED=lpat31"
    linux /lpat31.vmlinuz console=ttyS0,115200 module.sig_enforce=1 panic=-1 loglevel=5
    initrd /lpat31.initrd
}
GRUB
grub-script-check "$out/grub.cfg"
grub-mkstandalone -O x86_64-efi --locales= --fonts= --themes= \
    --modules='normal part_gpt fat linux serial loadenv search_fs_file' \
    -o BOOTX64.EFI "boot/grub/grub.cfg=$out/grub.cfg"
grub-editenv grubenv create
grub-editenv grubenv set saved_entry=mipad2-7215-lpat31-once next_entry=mipad2-ci-once
grub-editenv grubenv list > "$out/before.env"
printf 'fixture\n' > mipad2-release-fixture
truncate -s 128M esp.fat
mkfs.fat -F32 -n MIPAD2QUAL esp.fat
mmd -i esp.fat ::EFI ::EFI/BOOT
mcopy -i esp.fat BOOTX64.EFI ::EFI/BOOT/BOOTX64.EFI
mcopy -i esp.fat grubenv mipad2-release-fixture lpat31.vmlinuz lpat31.initrd candidate.initrd ::
mcopy -i esp.fat "$candidate/bzImage" ::candidate.vmlinuz
truncate -s 132M vm.raw
sgdisk --clear --new=1:2048:+128M --typecode=1:ef00 vm.raw > "$out/gpt.txt"
dd if=esp.fat of=vm.raw bs=1M seek=1 conv=notrunc status=none
cp /usr/share/OVMF/OVMF_VARS_4M.fd vars.fd
guest() {
    local boot=$1
    timeout 150s qemu-system-x86_64 \
        -machine q35,accel=tcg -cpu Westmere,family=6,model=76,stepping=3,movbe=on,rdrand=on \
        -smp 2 -m 1408 -nodefaults -display none -vga none -serial stdio -monitor none -nic none -no-reboot \
        -smbios type=1,manufacturer=CodexFixture,product=Mipad2 \
        -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
        -drive if=pflash,format=raw,file=vars.fd -drive if=ide,index=0,format=raw,file=vm.raw \
        < /dev/null > "$out/$boot.serial.log" 2>&1
    sed -E $'s/\x1b\\[[0-?]*[ -/]*[@-~]//g' "$out/$boot.serial.log" | tr -d '\r' > "$out/$boot.clean.log"
    mcopy -i 'vm.raw@@1048576' ::grubenv "$out/$boot.grubenv"
    grub-editenv "$out/$boot.grubenv" list > "$out/$boot.env"
    grep -Fxq saved_entry=mipad2-7215-lpat31-once "$out/$boot.env"
    if grep -Eq '^next_entry=.+|QUAL_(GRUBENV_WRITE_FAILED|FAILURE)=' "$out/$boot.env" "$out/$boot.clean.log"; then exit 12; fi
}
guest first
for mark in QUAL_GRUB_SELECTED=candidate QUAL_ONE_SHOT_CONSUMED=1 QUAL_PMC_TRACE_DEFAULT_OFF_AND_ISOLATED=1 \
            QUAL_SIGNED_MODULE_LOADS=11 QUAL_CANDIDATE_PASS=1; do
    grep -Fxq "$mark" "$out/first.clean.log"
done
guest second
grep -Fxq QUAL_GRUB_SELECTED=lpat31 "$out/second.clean.log"
grep -Fxq QUAL_FALLBACK_PASS=1 "$out/second.clean.log"
if grep -Fq QUAL_ONE_SHOT_CONSUMED=1 "$out/second.clean.log"; then exit 13; fi
cmp "$out/first.grubenv" "$out/second.grubenv"
printf 'PASS exact %s once, then LPAT31 fallback; saved_entry unchanged\n' "$expected" | tee "$out/result.txt"
