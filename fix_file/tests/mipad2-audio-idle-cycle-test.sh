#!/usr/bin/env bash
# Exercise PipeWire/TFA DSP start/idle transitions with digital silence.
set -Eeuo pipefail

expected="${EXPECTED_KERNEL:-6.14.0-mipad2-cachyos-navkeys}"
[[ "$(uname -r)" == "$expected" ]] || {
  echo "wrong kernel: $(uname -r)" >&2
  exit 2
}
for module in snd_soc_tfa98xx snd_soc_rt5659 snd_soc_sst_cht_bsw_rt5659; do
  [[ -r "/sys/module/$module/srcversion" ]] || { echo "module missing: $module" >&2; exit 3; }
  printf '%s ' "$module"
  cat "/sys/module/$module/srcversion"
done

uid=$(id -u)
export XDG_RUNTIME_DIR="/run/user/$uid"
[[ -S "$XDG_RUNTIME_DIR/pipewire-0" ]] || { echo "PipeWire socket missing" >&2; exit 4; }
command -v pw-cat >/dev/null
start=$(date '+%Y-%m-%d %H:%M:%S')
log="$HOME/mipad2-silent-idle-cycle-$(date +%Y%m%d-%H%M%S).log"
cycles=20
echo "start=$start cycles=$cycles playback=3s idle=7s; signal is digital silence"
for i in $(seq 1 "$cycles"); do
  echo "cycle=$i"
  rc=0
  timeout --signal=TERM 3s pw-cat --playback --raw --rate 48000 --channels 2 \
    --format s16 /dev/zero >/dev/null || rc=$?
  [[ $rc == 0 || $rc == 124 ]] || { echo "pw-cat failed: rc=$rc" >&2; exit "$rc"; }
  sleep 7
done

if journalctl -k -b --since "$start" --no-pager >"$log" 2>&1; then
  if grep -Eiq 'ret=-22|dsp_power_up timed out|BUG:|Oops:|Call Trace:' "$log"; then
    echo "kernel audio/driver error found; log=$log" >&2
    grep -Ein 'ret=-22|dsp_power_up timed out|BUG:|Oops:|Call Trace:' "$log" >&2
    exit 5
  fi
  for device in 00 01; do
    initialized=$(grep -Fc "i2c-tfa9890:$device: factory DSP init ret=0" "$log" || true)
    parked=$(grep -Fc "i2c-tfa9890:$device: playback idle; parking TFA DSP" "$log" || true)
    if (( initialized < cycles || parked < cycles )); then
      echo "insufficient DSP cycles on $device: initialized=$initialized parked=$parked expected>=$cycles" >&2
      exit 7
    fi
  done
  transitions=$(grep -Fc 'Mi Pad 2 AIF0 trigger cmd=1 active=1' "$log" || true)
  if (( transitions < cycles )); then
    echo "insufficient RT5659 playback starts: $transitions expected>=$cycles" >&2
    exit 8
  fi
  echo "PASS: no targeted kernel errors; log=$log"
else
  echo "Playback completed, but kernel journal was not readable; log=$log" >&2
  exit 6
fi
