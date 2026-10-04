#!/bin/bash
set -Eeuo pipefail

module=/tmp/codex-mipad2-tfa-dsp.ko
tone=/tmp/codex-mipad2-low-tone.wav
modname=snd_soc_tfa98xx_xiaomi
stock=/sys/bus/i2c/drivers/tfa989x
candidate=/sys/bus/i2c/drivers/tfa98xx
devices=(i2c-tfa9890:00 i2c-tfa9890:01)
expected_sha=205a52610c7d1f4de4f090231c9e6f14e36da4b6fe862679e0ff7b69e69ba522
switched=0
audio_stopped=0
audio_was_active=()
audio_state_saved=0

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
	rm -f "$module" "$tone"
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
stop_desktop_audio
echo "=== temporary driver switch ==="
for dev in "${devices[@]}"; do echo "$dev" > "$stock/unbind"; done
insmod "$module" defer_dsp_start=0
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
	if dmesg | grep -Fq 'factory container ready:'; then break; fi
	sleep 0.2
done
if ! dmesg | grep -F 'factory container ready:' | tail -n 4; then
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

echo "=== two bounded PipeWire/PulseAudio-routed speaker bursts ==="
timeout --signal=TERM --kill-after=3s 8s runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native paplay "$tone"
sleep 1
timeout --signal=TERM --kill-after=3s 8s runuser -u user -- env XDG_RUNTIME_DIR=/run/user/1000 PULSE_SERVER=unix:/run/user/1000/pulse/native paplay "$tone"
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
if ! dmesg | grep -E 'factory container ready:|factory DSP init ret=|Failed to read tfa98xx|DSP.*(fail|error)|tfa98xx.*(fail|error)' | tail -n 80; then
	echo "No matching TFA messages in dmesg"
fi
if dmesg | grep -E 'factory DSP init ret=-|factory container.*(invalid|fail)' | tail -n 10; then
	echo "DSP initialization reported an error" >&2
fi
if ! dmesg | grep -F 'factory DSP init ret=0' | tail -n 4; then
	echo "ERROR no successful factory DSP initialization was observed" >&2
	exit 1
fi
echo "DSP_TEST_BODY_COMPLETE"
