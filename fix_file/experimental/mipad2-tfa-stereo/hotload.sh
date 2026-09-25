#!/usr/bin/env bash
set -Eeuo pipefail

BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_KERNEL="$(cat "$BASE/kernel-release")"
AUDIO_USER="${MIPAD2_AUDIO_USER:-user}"
MACHINE_DEV="cht-bsw-rt5659"
TFA_DEVS=("i2c-tfa9890:00" "i2c-tfa9890:01")

RT5659="$BASE/snd-soc-rt5659.ko"
TFA98XX="$BASE/snd-soc-tfa98xx.ko"
MACHINE="$BASE/snd-soc-sst-cht-bsw-rt5659.ko"

uid_of_user() { id -u "$AUDIO_USER"; }
user_systemctl() {
    local uid
    uid="$(uid_of_user)"
    sudo -u "$AUDIO_USER" env         XDG_RUNTIME_DIR="/run/user/$uid"         DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus"         systemctl --user "$@"
}
user_run() {
    local uid
    uid="$(uid_of_user)"
    sudo -u "$AUDIO_USER" env         XDG_RUNTIME_DIR="/run/user/$uid"         DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus"         "$@"
}

stop_audio() {
    user_systemctl stop wireplumber.service 2>/dev/null || true
    user_systemctl stop pipewire-pulse.service pipewire-pulse.socket 2>/dev/null || true
    user_systemctl stop pipewire.service pipewire.socket 2>/dev/null || true
}

fix_audio_acl() {
    if command -v setfacl >/dev/null 2>&1; then
        setfacl -m "u:$AUDIO_USER:rw" /dev/snd/controlC* /dev/snd/pcmC* /dev/snd/timer 2>/dev/null || true
    fi
}

start_audio() {
    user_systemctl start pipewire.socket pipewire.service 2>/dev/null || true
    user_systemctl start wireplumber.service 2>/dev/null || true
    user_systemctl start pipewire-pulse.socket pipewire-pulse.service 2>/dev/null || true
}

unbind_machine() {
    if [ -e "/sys/bus/platform/drivers/$MACHINE_DEV/$MACHINE_DEV" ]; then
        echo "$MACHINE_DEV" > "/sys/bus/platform/drivers/$MACHINE_DEV/unbind"
    fi
}

unbind_tfa_from() {
    local drv="$1" dev
    for dev in "${TFA_DEVS[@]}"; do
        if [ -L "/sys/bus/i2c/devices/$dev/driver" ] &&
           [ "$(basename "$(readlink -f "/sys/bus/i2c/devices/$dev/driver")")" = "$drv" ]; then
            echo "$dev" > "/sys/bus/i2c/drivers/$drv/unbind"
        fi
    done
}

bind_tfa_to() {
    local drv="$1" dev
    for dev in "${TFA_DEVS[@]}"; do
        if [ ! -L "/sys/bus/i2c/devices/$dev/driver" ]; then
            echo "$dev" > "/sys/bus/i2c/drivers/$drv/bind"
        fi
    done
}

status_cmd() {
    echo "kernel=$(uname -r)"
    echo "machine_srcversion=$(cat /sys/module/snd_soc_sst_cht_bsw_rt5659/srcversion 2>/dev/null || echo none)"
    echo "rt5659_srcversion=$(cat /sys/module/snd_soc_rt5659/srcversion 2>/dev/null || echo none)"
    echo "tfa98xx_srcversion=$(cat /sys/module/snd_soc_tfa98xx/srcversion 2>/dev/null || echo none)"
    echo "bclk_ratio=$(cat /sys/module/snd_soc_sst_cht_bsw_rt5659/parameters/mipad2_aif2_bclk_ratio 2>/dev/null || echo n/a)"
    for dev in "${TFA_DEVS[@]}"; do
        if [ -L "/sys/bus/i2c/devices/$dev/driver" ]; then
            echo "$dev driver=$(basename "$(readlink -f "/sys/bus/i2c/devices/$dev/driver")")"
        else
            echo "$dev driver=unbound"
        fi
    done
    amixer -c0 cget name='left Stop' 2>/dev/null | tail -1 || true
    amixer -c0 cget name='right Stop' 2>/dev/null | tail -1 || true
}

wait_for_log() {
    local pattern="$1" i
    for i in $(seq 1 20); do
        if journalctl -k -b --since "$mark" --no-pager | grep -Fq "$pattern"; then
            return 0
        fi
        sleep 1
    done
    echo "[apply] timeout waiting for kernel log: $pattern" >&2
    journalctl -k -b --since "$mark" --no-pager | tail -100 >&2
    return 1
}

rollback() {
    set +e
    echo "[rollback] restoring stock stable audio stack"
    stop_audio
    unbind_machine
    modprobe -r snd_soc_sst_cht_bsw_rt5659 2>/dev/null || true

    unbind_tfa_from tfa98xx
    modprobe -r snd_soc_rt5659 2>/dev/null || true
    rmmod snd_soc_tfa98xx 2>/dev/null || true
    modprobe snd_soc_rt5659

    bind_tfa_to tfa989x

    modprobe snd_soc_sst_cht_bsw_rt5659
    sleep 2
    fix_audio_acl
    start_audio
    sleep 2
    status_cmd
}

apply() {
    [ "$(uname -r)" = "$EXPECTED_KERNEL" ] || {
        echo "Refusing: expected $EXPECTED_KERNEL, got $(uname -r)" >&2
        exit 2
    }
    for f in "$RT5659" "$TFA98XX" "$MACHINE"; do
        [ -s "$f" ] || { echo "Missing $f" >&2; exit 3; }
    done

    local mark pw_pid
    mark="$(date '+%Y-%m-%d %H:%M:%S')"

    trap 'rc=$?; failed_line=$LINENO; failed_cmd=$BASH_COMMAND; trap - ERR; printf "[apply] failed rc=%s line=%s cmd=%s\n" "$rc" "$failed_line" "$failed_cmd"; rollback; exit "$rc"' ERR

    stop_audio
    unbind_machine
    modprobe -r snd_soc_sst_cht_bsw_rt5659

    unbind_tfa_from tfa989x
    unbind_tfa_from tfa98xx
    modprobe -r snd_soc_rt5659
	# A prior hotload leaves the old TFA module resident even after unbind.
	rmmod snd_soc_tfa98xx 2>/dev/null || true

    insmod "$TFA98XX" defer_dsp_start=1

    sleep 1
    bind_tfa_to tfa98xx
    insmod "$RT5659"
    for dev in "${TFA_DEVS[@]}"; do
        [ "$(basename "$(readlink -f "/sys/bus/i2c/devices/$dev/driver")")" = "tfa98xx" ]
    done

    echo 0 > /sys/bus/i2c/devices/i2c-tfa9890:00/monitor
    echo 0 > /sys/bus/i2c/devices/i2c-tfa9890:01/monitor

    insmod "$MACHINE"
    sleep 2
    fix_audio_acl
    grep -q "cht-bsw-rt5659" /proc/asound/cards
    [ "$(cat /sys/module/snd_soc_sst_cht_bsw_rt5659/parameters/mipad2_aif2_bclk_ratio)" = "64" ]

    start_audio
    sleep 2

    # Keep real AIF2 clocks active while releasing the two factory DSPs.
    (
        trap - ERR
        user_run timeout 8s pw-cat --playback --raw --rate 48000 --channels 2 --format s16 /dev/zero >/dev/null 2>&1 || true
    ) &
    pw_pid=$!
    sleep 2

    echo N > /sys/module/snd_soc_tfa98xx/parameters/defer_dsp_start
    amixer -c0 cset name='left Stop' off >/dev/null
    amixer -c0 cset name='right Stop' off >/dev/null
    sleep 3

    wait_for_log 'i2c-tfa9890:00: factory DSP init ret=0'
    wait_for_log 'i2c-tfa9890:01: factory DSP init ret=0'

    echo 1 > /sys/bus/i2c/devices/i2c-tfa9890:00/monitor
    echo 1 > /sys/bus/i2c/devices/i2c-tfa9890:01/monitor
    wait "$pw_pid" 2>/dev/null || true

    # Verify idle stability, then verify automatic DSP recovery on new playback.
    sleep 12
    if journalctl -k -b --since "$mark" --no-pager | grep -Eq 'ret=-22|dsp_power_up timed out'; then
        echo "[apply] DSP failure appeared during idle" >&2
        return 1
    fi
    logs="$(journalctl -k -b --since "$mark" --no-pager)"
    printf '%s\n' "$logs" | grep -Fq 'i2c-tfa9890:00: playback idle; parking TFA DSP'
    printf '%s\n' "$logs" | grep -Fq 'i2c-tfa9890:01: playback idle; parking TFA DSP'

    local mark2
    mark2="$(date '+%Y-%m-%d %H:%M:%S')"
    (
        trap - ERR
        user_run timeout 8s pw-cat --playback --raw --rate 48000 --channels 2 --format s16 /dev/zero >/dev/null 2>&1 || true
    ) &
    pw_pid=$!
    sleep 2
    amixer -c0 cset name='left Stop' off >/dev/null
    amixer -c0 cset name='right Stop' off >/dev/null
    for i in $(seq 1 20); do
        logs="$(journalctl -k -b --since "$mark2" --no-pager)"
        if printf '%s\n' "$logs" | grep -Fq 'i2c-tfa9890:00: factory DSP init ret=0' &&
           printf '%s\n' "$logs" | grep -Fq 'i2c-tfa9890:01: factory DSP init ret=0' &&
           printf '%s\n' "$logs" | grep -Fq 'DAI trigger id=0 cmd=1'; then
            break
        fi
        sleep 1
    done
    wait "$pw_pid" 2>/dev/null || true
    sleep 2
    logs="$(journalctl -k -b --since "$mark2" --no-pager)"
    printf '%s\n' "$logs" | grep -Fq 'i2c-tfa9890:00: factory DSP init ret=0'
    printf '%s\n' "$logs" | grep -Fq 'i2c-tfa9890:01: factory DSP init ret=0'
    printf '%s\n' "$logs" | grep -Fq 'DAI trigger id=0 cmd=1'
    if printf '%s\n' "$logs" | grep -Eq 'ret=-22|dsp_power_up timed out'; then
        echo "[apply] DSP recovery emitted a failure" >&2
        return 1
    fi

    trap - ERR
    echo "[apply] dual TFA9890 stereo hotload OK"
    status_cmd
}

case "${1:-status}" in
    apply) apply ;;
    rollback) rollback ;;
    status) status_cmd ;;
    *) echo "usage: $0 {apply|rollback|status}" >&2; exit 64 ;;
esac
