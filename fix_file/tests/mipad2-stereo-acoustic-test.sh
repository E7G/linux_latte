#!/usr/bin/env bash
# Low-volume stereo acoustic loopback using the tablet's built-in microphone.
# Requires PipeWire, alsa-utils and Python 3. Does not alter kernel modules.
set -Eeuo pipefail

card=0
sink=@DEFAULT_AUDIO_SINK@
if ! wpctl inspect "$sink" | grep -Fq 'HiFi__Speaker__sink'; then
    echo 'Select the built-in Speaker output before acoustic testing.' >&2
    exit 2
fi
raw=$(mktemp --suffix=.raw)
rec=$(mktemp --suffix=.wav)
old_volume=$(wpctl get-volume "$sink" | awk '{print $2}')
old_muted=0
wpctl get-volume "$sink" | grep -q '\[MUTED\]' && old_muted=1 || true
get_ctl() {
    amixer -c "$card" cget "name=$1" | sed -n 's/^ *: values=//p' | tail -1
}
old_sto1=$(get_ctl 'STO1 ADC Capture Switch')
old_in3=$(get_ctl 'IN3 Boost Volume')
old_in4=$(get_ctl 'IN4 Boost Volume')
record_pid=
cleanup() {
    if [ -n "$record_pid" ]; then
        kill "$record_pid" 2>/dev/null || true
        wait "$record_pid" 2>/dev/null || true
    fi
    amixer -c "$card" cset name='STO1 ADC Capture Switch' "$old_sto1" >/dev/null 2>&1 || true
    amixer -c "$card" cset name='IN3 Boost Volume' "$old_in3" >/dev/null 2>&1 || true
    amixer -c "$card" cset name='IN4 Boost Volume' "$old_in4" >/dev/null 2>&1 || true
    wpctl set-volume "$sink" "$old_volume" >/dev/null 2>&1 || true
    wpctl set-mute "$sink" "$old_muted" >/dev/null 2>&1 || true
    rm -f "$raw" "$rec"
}
trap cleanup EXIT

amixer -c "$card" cset name='STO1 ADC Capture Switch' on,on >/dev/null
amixer -c "$card" cset name='IN3 Boost Volume' 20 >/dev/null
amixer -c "$card" cset name='IN4 Boost Volume' 20 >/dev/null
wpctl set-volume "$sink" 0.25
wpctl set-mute "$sink" 0

python3 - "$raw" <<'PY'
import math, struct, sys
rate=48000
with open(sys.argv[1],'wb') as out:
    for i in range(int(4.5*rate)):
        t=i/rate
        left = int(7000*math.sin(2*math.pi*440*t)) if 0.5 <= t < 2.0 else 0
        right = int(7000*math.sin(2*math.pi*880*t)) if 2.5 <= t < 4.0 else 0
        out.write(struct.pack('<hh',left,right))
PY

arecord -D hw:0,0 -f S16_LE -r 48000 -c 2 -d 6 "$rec" >/dev/null 2>&1 &
record_pid=$!
sleep 0.5
pw-cat --playback --raw --rate 48000 --channels 2 --format s16 \
    --volume 0.7 "$raw" >/dev/null 2>&1
wait "$record_pid"
record_pid=

python3 - "$rec" <<'PY'
import array, math, sys, wave
with wave.open(sys.argv[1]) as w:
    rate=w.getframerate()
    channels=w.getnchannels()
    data=array.array('h',w.readframes(w.getnframes()))
if sys.byteorder != 'little':
    data.byteswap()
if rate != 48000 or channels != 2:
    raise SystemExit('unexpected recording format')

def amplitude(start,end,freq):
    a=int(start*rate); b=int(end*rate)
    n=b-a
    result=[]
    for ch in range(2):
        real=imag=0.0
        for j,i in enumerate(range(a,b)):
            x=data[2*i+ch]
            phase=2*math.pi*freq*j/rate
            real+=x*math.cos(phase)
            imag+=x*math.sin(phase)
        result.append(2*math.hypot(real,imag)/n)
    return max(result)

quiet440=amplitude(.1,.4,440)
quiet880=amplitude(.1,.4,880)
left=amplitude(1.2,2.2,440)
right=amplitude(3.2,4.2,880)
left_ok=left>max(3*quiet440,3)
right_ok=right>max(3*quiet880,3)
print(f'left  440 Hz: {left:.2f} (quiet {quiet440:.2f})', 'PASS' if left_ok else 'FAIL')
print(f'right 880 Hz: {right:.2f} (quiet {quiet880:.2f})', 'PASS' if right_ok else 'FAIL')
if not (left_ok and right_ok):
    raise SystemExit(1)
PY
