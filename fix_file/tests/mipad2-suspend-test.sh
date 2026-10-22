#!/bin/sh
# Active Mi Pad 2 s2idle/S0ix regression test.
# This deliberately suspends the tablet and uses RTC wakeup.
set -eu

seconds=${1:-8}
case "$seconds" in
    *[!0-9]*|'') echo "Usage: $0 [seconds]" >&2; exit 2 ;;
esac
[ "$seconds" -ge 3 ] || { echo "Refusing suspend shorter than 3 seconds" >&2; exit 2; }

if [ "$(id -u)" -ne 0 ]; then
    exec sudo "$0" "$@"
fi

pmc=/sys/kernel/debug/pmc_atom/sleep_state
[ -r "$pmc" ] || { echo "MISS pmc_atom sleep_state (is debugfs mounted?)" >&2; exit 1; }
command -v rtcwake >/dev/null 2>&1 || { echo "MISS rtcwake" >&2; exit 1; }

s0i3_us()
{
    awk '/S0I3 Residency:/ {
        value=$3
        sub(/us$/, "", value)
        print value
        exit
    }' "$pmc"
}

before=$(s0i3_us)
[ -n "$before" ] || { echo "MISS S0I3 residency counter" >&2; exit 1; }
start=$(date --iso-8601=seconds)

printf 'INFO S0I3 before: %sus\n' "$before"
printf 'INFO suspending for %ss with RTC wake\n' "$seconds"
rtcwake -m mem -s "$seconds"

after=$(s0i3_us)
[ -n "$after" ] || { echo "MISS S0I3 residency counter after resume" >&2; exit 1; }
delta=$((after - before))
printf 'INFO S0I3 after:  %sus\n' "$after"
printf 'INFO S0I3 delta:  %sus\n' "$delta"

# Allow for entry/exit latency but require most of the requested interval in S0i3.
minimum=$((seconds * 700000))
fail=0
if [ "$delta" -ge "$minimum" ]; then
    printf 'OK   S0I3 residency increased sufficiently\n'
else
    printf 'MISS S0I3 residency increased only %sus (minimum %sus)\n' "$delta" "$minimum"
    fail=1
fi

if command -v mipad2-hardware-smoke >/dev/null 2>&1; then
    mipad2-hardware-smoke || fail=1
elif [ -x /usr/local/libexec/mipad2-hardware-smoke ]; then
    /usr/local/libexec/mipad2-hardware-smoke || fail=1
fi

resume_log=$(journalctl -k -b --since "$start" --no-pager 2>/dev/null || true)
if printf '%s\n' "$resume_log" | grep -Eqi     'DSP subsystem start timed out|DSP power-up timed out|warm DSP resume failed.*forcing cold restart.*(failed|timeout)'; then
    printf 'MISS TFA DSP resume error detected\n'
    printf '%s\n' "$resume_log" | grep -Ei         'tfa98|DSP subsystem start timed out|DSP power-up timed out|warm DSP resume failed' | tail -n 80
    fail=1
else
    printf 'OK   no TFA DSP resume timeout detected\n'
fi

exit "$fail"
