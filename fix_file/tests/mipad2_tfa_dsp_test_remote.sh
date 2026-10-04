#!/bin/bash
set -Eeuo pipefail

module=/tmp/codex-mipad2-tfa-dsp.ko
tone=/tmp/codex-mipad2-low-tone.wav
modname=snd_soc_tfa98xx_xiaomi
stock=/sys/bus/i2c/drivers/tfa989x
candidate=/sys/bus/i2c/drivers/tfa98xx
devices=(i2c-tfa9890:00 i2c-tfa9890:01)
expected_sha=b2c919735b4814aa7914d277bdb284ba99e2723559ef4a6aeec0f752838fdbe7
switched=0
audio_stopped=0
audio_was_active=()
audio_state_saved=0
debug_control=/sys/kernel/debug/dynamic_debug/control
debug_enabled=0
test_audio_sink=
saved_sink_volume=
saved_speaker_volume=
saved_mono_volume=
audio_levels_saved=0
test_mode=${MIPAD2_TFA_TEST_MODE:-silent}
case "$test_mode" in silent|audible) ;; *) echo 'Invalid test mode' >&2; exit 2;; esac
test_stop_control=${MIPAD2_TFA_TEST_STOP_CONTROL:-0}
case "$test_stop_control" in 0|1) ;; *) echo 'Invalid stop-control test flag' >&2; exit 2;; esac
[[ "$test_stop_control" == 0 || "$test_mode" == silent ]] || { echo 'Stop-control testing requires silent mode' >&2; exit 2; }
log_checker=/tmp/mipad2_tfa_dsp_log_check.py
log_raw=$(mktemp /tmp/mipad2-tfa-dsp-log.XXXXXX)
log_marker=MIPAD2_TFA_DSP_BEGIN_$$-$(date +%s%N)

capture_current_log() {
	dmesg --color=never > "$log_raw"
}

set_tfa_debug() {
	local flag=$1 fn
	for fn in tfa98xx_trigger tfa98xx_dsp_init tfa98xx_digital_mute tfa98xx_monitor; do
		printf 'module %s func %s %s\n' "$modname" "$fn" "$flag" > "$debug_control"
	done
}

audio_control() {
	runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user "$@"
}

wait_for_no_sound_users() {
	if ! command -v fuser >/dev/null 2>&1; then
		echo "ERROR fuser is required to prove ALSA file handles are closed" >&2
		return 1
	fi
	for attempt in {1..50}; do
		if ! fuser -s /dev/snd/* >/dev/null 2>&1; then return 0; fi
		sleep 0.1
	done
	fuser -v /dev/snd/* >&2 || true
	return 1
}

capture_audio_state() {
	local unit
	for unit in pipewire.socket pipewire-pulse.socket pipewire.service pipewire-pulse.service wireplumber.service; do
		if audio_control is-active --quiet "$unit"; then
			audio_was_active+=("$unit")
		fi
	done
	audio_state_saved=1
}

stop_desktop_audio() {
	if [[ "$audio_state_saved" != 1 ]]; then capture_audio_state; fi
	audio_stopped=1
	if ((${#audio_was_active[@]})); then
		audio_control stop wireplumber.service pipewire-pulse.service pipewire.service pipewire-pulse.socket pipewire.socket
	fi
	wait_for_no_sound_users
}

unit_was_active() {
	local want=$1 unit
	for unit in "${audio_was_active[@]}"; do
		[[ "$unit" == "$want" ]] && return 0
	done
	return 1
}

start_desktop_audio() {
	[[ "$audio_stopped" == 1 ]] || return 0
	if ((${#audio_was_active[@]})); then
		if ! audio_control start "${audio_was_active[@]}"; then
			return 1
		fi
		sleep 2
	fi
	audio_stopped=0
}

restore_desktop_audio() {
	[[ "$audio_stopped" == 1 ]] || return 0
	echo "=== restoring original PipeWire/WirePlumber state ==="
	if ! start_desktop_audio; then
		echo "ERROR could not restore original user audio services" >&2
		status=1
	fi
	if unit_was_active pipewire-pulse.service || unit_was_active pipewire-pulse.socket; then
		sink_list=$(runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl list short sinks 2>&1)
		printf '%s\n' "$sink_list"
		if grep -Fq 'alsa_output.platform-cht-bsw-rt5659' <<<"$sink_list"; then
			echo "AUDIO_RESTORED=yes"
		else
			echo "ERROR PipeWire HiFi speaker sink did not restore" >&2
			status=1
		fi
	else
		echo "AUDIO_RESTORED=not-needed"
	fi
}

get_alsa_playback_percent() {
	amixer -c 0 get "$1" 2>/dev/null |
		awk -F'[][]' '/Playback/ { for (i = 2; i <= NF; i += 2) if ($i ~ /^[0-9.]+%$/) { print $i; exit } }'
}

save_test_audio_levels() {
	test_audio_sink=$(runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl get-default-sink)
	if [[ "$test_audio_sink" != *alsa_output.platform-cht-bsw-rt5659* ]]; then
		echo "ERROR default sink is not the Mi Pad 2 HiFi speaker: $test_audio_sink" >&2
		return 1
	fi
	saved_sink_volume=$(runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl get-sink-volume "$test_audio_sink" |
		awk 'NR == 1 { for (i = 1; i <= NF; i++) if ($i ~ /%$/) { print $i; exit } }')
	saved_speaker_volume=$(get_alsa_playback_percent Speaker)
	saved_mono_volume=$(get_alsa_playback_percent Mono)
	if [[ -z "$saved_sink_volume" || -z "$saved_speaker_volume" || -z "$saved_mono_volume" ]]; then
		echo "ERROR could not snapshot speaker levels for safe restoration" >&2
		return 1
	fi
	audio_levels_saved=1
	echo "Saved audio levels: sink=$test_audio_sink $saved_sink_volume Speaker=$saved_speaker_volume Mono=$saved_mono_volume"
}

set_test_audio_levels() {
	runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl set-sink-volume "$test_audio_sink" 80%
	amixer -c 0 sset Speaker 80% >/dev/null
	amixer -c 0 sset Mono 80% >/dev/null
	echo "Temporary playback levels: PipeWire/Speaker/Mono=80%"
}

restore_test_audio_levels() {
	[[ "$audio_levels_saved" == 1 ]] || return 0
	if [[ "$audio_stopped" != 1 ]]; then
		runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl set-sink-volume "$test_audio_sink" "$saved_sink_volume" || status=1
	fi
	amixer -c 0 sset Speaker "$saved_speaker_volume" >/dev/null || status=1
	amixer -c 0 sset Mono "$saved_mono_volume" >/dev/null || status=1
	echo "Restored audio levels: PipeWire=$saved_sink_volume Speaker=$saved_speaker_volume Mono=$saved_mono_volume"
}

capture_active_playback_state() {
	local f name
	echo "=== active playback DAPM widgets ==="
	for f in /sys/kernel/debug/asoc/cht-bsw-rt5659/dapm/* \
		/sys/kernel/debug/asoc/cht-bsw-rt5659/i2c-tfa9890:00/dapm/* \
		/sys/kernel/debug/asoc/cht-bsw-rt5659/i2c-tfa9890:01/dapm/*; do
		[[ -r "$f" ]] || continue
		name=${f##*/}
		case "$name" in
			*Speaker*|*AIF2*|*TFA*|*HiFi*|AIFIN*|AMPE*|POWER*|"OUT Left"|"OUT Right"|"NXP Output Mixer"|"Ext Spk")
				printf '%s=' "$name"
				tr '\n' ' ' < "$f"
				printf '\n'
				;;
		esac
	done
	echo "=== active TFA register snapshot ==="
	for f in /sys/kernel/debug/regmap/*/registers; do
		case "$f" in
			*tfa*|*TFA*|*9890*) echo "--- $f"; sed -n '1,24p' "$f";;
		esac
	done
}

verify_tfa_registers() {
	python3 - "$1" <<'PY'
from pathlib import Path
import sys
state = sys.argv[1]
assert state in ('active', 'idle')
for dev in ('i2c-tfa9890:00', 'i2c-tfa9890:01'):
    # The candidate uses REGCACHE_NONE: these are real hardware reads.
    path = Path('/sys/kernel/debug/regmap') / dev / 'registers'
    values = {int(k,16): int(v,16) for k,v in
              (line.split(':',1) for line in path.read_text().splitlines())}
    status, sysctrl = values[0], values[9]
    if state == 'active':
        assert status & 0xc002 == 0xc002, (dev, 'PLL/amp/reference', hex(status))
        assert not status & 0x200, (dev, 'NOCLK', hex(status))
        assert sysctrl & 0x1c == 0x1c and not sysctrl & 1, (dev, 'CFE/AMPE/DCA/PWDN', hex(sysctrl))
        assert values[4] & 0xc0 == 0x80, (dev, 'amplifier input is not DSP')
        assert values[0x80] & 3 == 3, (dev, 'factory calibration not completed')
    else:
        assert sysctrl & 1, (dev, 'PWDN not set after stop', hex(sysctrl))
        assert not status & 0xc000, (dev, 'reference/amp still up after stop', hex(status))
    print(f'PASS {state} {dev}: status={status:04x} sys={sysctrl:04x} MTP={values[0x80]:04x}')
PY
}

restore() {
	status=$?
	trap - EXIT INT TERM
	set +e
	echo "=== restoring stock 6.14 TFA989X driver ==="
	for dev in "${devices[@]}"; do
		path="/sys/bus/i2c/devices/$dev/driver"
		if [[ -L "$path" ]] && [[ "$(basename "$(readlink -f "$path")")" == tfa98xx ]]; then
			switched=1
		fi
	done
	if [[ "$switched" == 1 && "$audio_stopped" != 1 ]]; then
		if ! stop_desktop_audio; then
			echo "ERROR could not quiesce all ALSA users before candidate unbind" >&2
			status=1
		fi
	fi
	safe_to_unbind=1
	if [[ "$switched" == 1 ]] && ! wait_for_no_sound_users; then
		echo "ERROR ALSA clients still hold /dev/snd handles; refusing driver unbind" >&2
		safe_to_unbind=0
		status=1
	fi
	for dev in "${devices[@]}"; do
		path="/sys/bus/i2c/devices/$dev/driver"
		if [[ "$safe_to_unbind" == 1 ]] && [[ -L "$path" ]] && [[ "$(basename "$(readlink -f "$path")")" == tfa98xx ]]; then
			echo "$dev" > "$candidate/unbind"
		fi
	done
	if [[ "$debug_enabled" == 1 ]] && [[ -w "$debug_control" ]]; then
		set_tfa_debug -p || status=1
		debug_enabled=0
	fi
	if [[ "$safe_to_unbind" == 1 ]] && [[ -e "/sys/module/$modname" ]]; then
		switched=1
		rmmod "$modname"
	fi
	for dev in "${devices[@]}"; do
		path="/sys/bus/i2c/devices/$dev/driver"
		if [[ ! -L "$path" ]] || [[ "$(basename "$(readlink -f "$path")")" != tfa989x ]]; then
			echo "$dev" > "$stock/bind"
		fi
	done
	sleep 1
	for dev in "${devices[@]}"; do
		path="/sys/bus/i2c/devices/$dev/driver"
		printf 'RESTORED %s=' "$dev"
		if [[ -L "$path" ]]; then
			driver=$(basename "$(readlink -f "$path")")
			echo "$driver"
			if [[ "$driver" != tfa989x ]]; then status=1; fi
		else
			echo unbound
			status=1
		fi
	done
	if [[ -e "/sys/module/$modname" ]]; then
		echo "ERROR candidate module still loaded" >&2
		status=1
	fi
	cat /proc/asound/cards
	if ! grep -Fq 'cht-bsw-rt5659' /proc/asound/cards; then status=1; fi
	mp2-test-no-idle status
	if [[ "$(uname -r)" != 6.14.0-mipad2-cachyos ]]; then status=1; fi
	if [[ "$(systemctl is-system-running)" != running ]]; then status=1; fi
	restore_desktop_audio
	restore_test_audio_levels
	rm -f "$module" "$tone" "$log_raw"
	exit "$status"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=== DSP test preflight ==="
mp2-test-no-idle status
[[ "$(uname -r)" == 6.14.0-mipad2-cachyos ]]
[[ ! -e "/sys/module/$modname" ]]
[[ -s "$module" && -s "$tone" ]]
[[ "$(sha256sum "$module" | cut -d' ' -f1)" == "$expected_sha" ]]
grep -Fq 'cht-bsw-rt5659' /proc/asound/cards

for dev in "${devices[@]}"; do
	path="/sys/bus/i2c/devices/$dev/driver"
	[[ -L "$path" ]]
	[[ "$(basename "$(readlink -f "$path")")" == tfa989x ]]
done
if command -v fuser >/dev/null 2>&1 && fuser -s /dev/snd/pcmC0D0p /dev/snd/pcmC0D1p; then
	echo "Refusing: active ALSA PCM users" >&2
	exit 1
fi
command -v timeout >/dev/null
command -v paplay >/dev/null
command -v python3 >/dev/null
[[ -f "$log_checker" ]]
if [[ "$test_mode" == silent ]]; then
	python3 - "$tone" <<'PY'
import sys
import wave
with wave.open(sys.argv[1], 'rb') as pcm:
    assert (pcm.getnchannels(), pcm.getsampwidth(), pcm.getframerate()) == (2, 2, 48000)
    assert pcm.getnframes() == 288000, 'silent test must last six seconds'
    assert not any(pcm.readframes(pcm.getnframes())), 'silent test contains nonzero PCM'
PY
fi
save_test_audio_levels
stop_desktop_audio
echo "=== temporary driver switch ==="
printf '%s\n' "$log_marker" > /dev/kmsg
for dev in "${devices[@]}"; do echo "$dev" > "$stock/unbind"; done
insmod "$module" defer_dsp_start=0
[[ -w "$debug_control" ]]
set_tfa_debug +p
debug_enabled=1
echo "Enabled dynamic debug for TFA playback/init callbacks"
for dev in "${devices[@]}"; do
	path="/sys/bus/i2c/devices/$dev/driver"
	for attempt in {1..20}; do
		[[ -L "$path" ]] && break
		sleep 0.1
	done
	if [[ ! -L "$path" ]]; then echo "$dev" > "$candidate/bind"; fi
	[[ -L "$path" ]]
	[[ "$(basename "$(readlink -f "$path")")" == tfa98xx ]]
	echo "BOUND $dev=tfa98xx"
done

for attempt in {1..30}; do
	capture_current_log
	if python3 "$log_checker" "$log_raw" "$log_marker" --containers-only >/dev/null 2>&1; then break; fi
	sleep 0.2
done
capture_current_log
if ! python3 "$log_checker" "$log_raw" "$log_marker" --containers-only; then
	echo "ERROR factory container was not loaded" >&2
	exit 1
fi
grep -Fq 'cht-bsw-rt5659' /proc/asound/cards
for dev in "${devices[@]}"; do
	if [[ -r "/sys/bus/i2c/devices/$dev/monitor" ]]; then
		printf 'MONITOR %s=' "$dev"
		cat "/sys/bus/i2c/devices/$dev/monitor"
	fi
done

start_desktop_audio
echo "=== waiting for the OEM HiFi speaker route ==="
for attempt in {1..30}; do
	sink_list=$(runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl list short sinks 2>&1) || true
	if grep -Fq 'alsa_output.platform-cht-bsw-rt5659' <<<"$sink_list"; then break; fi
	sleep 0.2
done
printf '%s\n' "$sink_list"
if ! grep -Fq 'alsa_output.platform-cht-bsw-rt5659' <<<"$sink_list"; then
	echo "ERROR OEM HiFi speaker route did not appear" >&2
	exit 1
fi
if [[ "$test_mode" == audible ]]; then set_test_audio_levels; fi

echo "=== bounded PipeWire speaker test: mode=$test_mode ==="
bursts=2
for ((burst=1; burst<=bursts; burst++)); do
	(timeout --signal=TERM --kill-after=3s 8s runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native paplay "$tone") &
	playback_pid=$!
	sleep 0.25
	echo "=== playback burst $burst ==="
	capture_active_playback_state
	if [[ "$test_mode" == silent ]]; then
		# Initial full firmware loading is slower than an owned warm restart.
		# Keep the settled gate separate from the early diagnostic snapshot.
		sleep 2
		echo "=== settled factory DSP state (PCM remains active) ==="
		grep -q 'state: RUNNING' /proc/asound/chtbswrt5659/pcm0p/sub0/status
		capture_active_playback_state
		verify_tfa_registers active
		if [[ "$test_stop_control" == 1 && "$burst" == 1 ]]; then
			echo '=== stop controls during active digital-zero PCM ==='
			amixer -c 0 cset name='left Stop' 1
			amixer -c 0 cset name='right Stop' 1
			sleep 0.2
			grep -q 'state: RUNNING' /proc/asound/chtbswrt5659/pcm0p/sub0/status
			verify_tfa_registers idle
			for dev in "${devices[@]}"; do
				[[ "$(cat "/sys/bus/i2c/devices/$dev/monitor")" == 0 ]]
				 echo "PASS stopped monitor $dev=0"
			done
			amixer -c 0 cset name='left Stop' 0
			amixer -c 0 cset name='right Stop' 0
			sleep 0.5
			grep -q 'state: RUNNING' /proc/asound/chtbswrt5659/pcm0p/sub0/status
			verify_tfa_registers active
			for dev in "${devices[@]}"; do
				[[ "$(cat "/sys/bus/i2c/devices/$dev/monitor")" == 1 ]]
				echo "PASS restarted monitor $dev=1"
			done
		fi
	fi
	wait "$playback_pid"
	if [[ "$test_mode" == silent ]]; then
		# Wait through PipeWire's suspend timeout without stopping its services.
		# A mute must not leave queued init able to repower the now-idle amp.
		sleep 7
		grep -q closed /proc/asound/chtbswrt5659/pcm0p/sub0/status
		verify_tfa_registers idle
	elif [[ "$burst" != "$bursts" ]]; then
		sleep 1
	fi
done
for attempt in {1..30}; do
	sink_inputs=$(runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native pactl list short sink-inputs 2>&1) || true
	[[ -z "$sink_inputs" ]] && break
	sleep 0.2
done
if [[ -n "$sink_inputs" ]]; then
	echo "ERROR playback sink input did not close" >&2
	printf '%s\n' "$sink_inputs" >&2
	exit 1
fi
stop_desktop_audio

echo "=== TFA DSP logs ==="
capture_current_log
if ! awk -v marker="$log_marker" 'index($0, marker) { found=1; next } found' "$log_raw" | grep -E 'factory container ready:|factory DSP init ret=|tfa98xx_trigger|tfa98xx_dsp_init|tfa98xx_digital_mute|tfa98xx_monitor|Failed to read tfa98xx|DSP.*(fail|error)|tfa98xx.*(fail|error)' | tail -n 120; then
	echo "No matching TFA messages in dmesg"
fi
if ! python3 "$log_checker" "$log_raw" "$log_marker"; then
	echo "ERROR both current-run factory DSP initializations were not successful" >&2
	exit 1
fi
echo "DSP_TEST_BODY_COMPLETE"
