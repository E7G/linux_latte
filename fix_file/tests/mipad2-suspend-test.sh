#!/bin/sh
# Active Mi Pad 2 s2idle/S0ix regression test.
# This deliberately suspends the tablet and uses RTC wakeup.
set -eu

fail_run()
{
    printf 'MISS %s\n' "$*" >&2
    exit 1
}

seconds=${1:-8}
[ "$#" -le 1 ] || fail_run "Usage: $0 [seconds: 3-300]"
case "$seconds" in
    [1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;;
    *) fail_run "Usage: $0 [seconds: 3-300]" ;;
esac
[ "$seconds" -ge 3 ] && [ "$seconds" -le 300 ] ||
    fail_run "Suspend duration must be 3-300 seconds"
if [ "$(id -u)" -ne 0 ]; then
    exec sudo /bin/sh "$0" "$@"
fi

for tool in rtcwake systemctl busctl python3 journalctl flock; do
    command -v "$tool" >/dev/null 2>&1 || fail_run "$tool is required"
done
[ "$(cat /sys/class/dmi/id/sys_vendor)" = 'Xiaomi Inc' ] &&
[ "$(cat /sys/class/dmi/id/product_name)" = Mipad2 ] ||
    fail_run "This test is for the Xiaomi Mi Pad 2 only"
[ "$(cat /proc/1/comm)" = systemd ] || fail_run "No systemd/logind; not suspending"
[ "$(cat /sys/power/mem_sleep)" = '[s2idle]' ] || fail_run "Expected firmware s2idle mode"

pmc=/sys/kernel/debug/pmc_atom/sleep_state
rtc=/sys/class/rtc/rtc0
irq=/sys/power/pm_wakeup_irq
rtc_events=/sys/firmware/acpi/interrupts/ff_rt_clk
[ -r "$pmc" ] && [ -r "$rtc/wakealarm" ] && [ -r "$rtc/since_epoch" ] &&
[ -r "$irq" ] && [ -r "$rtc_events" ] ||
    fail_run "PMC, RTC fixed-event counter or wake-IRQ evidence is unavailable"

umask 077
exec 9>>/run/mipad2-suspend-test.lock
flock -n 9 || fail_run "Another Mi Pad 2 suspend test is active"

check_no_sleep_inhibitor()
{
    inhibitors=$(busctl --system --timeout=5s --json=short call org.freedesktop.login1 \
        /org/freedesktop/login1 org.freedesktop.login1.Manager ListInhibitors) || return
    INHIBITORS="$inhibitors" python3 -B - <<'PY'
import json
import os

reply = json.loads(os.environ["INHIBITORS"])
data = reply.get("data")
if reply.get("type") != "a(ssssuu)" or not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], list):
    raise SystemExit("Invalid logind inhibitor response")
for row in data[0]:
    if (not isinstance(row, list) or len(row) != 6
        or not all(isinstance(item, str) for item in row[:4])
        or not all(type(item) is int and item >= 0 for item in row[4:])
        or row[3] not in {"block", "block-weak", "delay"}):
        raise SystemExit("Unknown logind inhibitor entry")
    if "sleep" in row[0].split(":") and row[3] != "delay":
        raise SystemExit("Sleep is inhibited; no suspend was requested")
PY
}

s0i3_us()
{
    awk '/S0I3 Residency:/ {
        value=$3
        sub(/us$/, "", value)
        if (value ~ /^[0-9]+$/)
            print value
        exit
    }' "$pmc"
}

check_no_alarm()
{
    existing=$(cat "$rtc/wakealarm") || return
    [ -z "$existing" ]
}

rtc_event_count()
{
    awk '
        NR == 1 && $1 ~ /^[0-9]+$/ && $1 <= 4294967295 { count = $1 + 0; valid = 1 }
        END {
            if (NR != 1 || !valid) exit 1
            printf "%.0f\n", count
        }' "$rtc_events"
}

check_no_sleep_inhibitor || fail_run "Cannot confirm suspend is allowed"
check_no_alarm || fail_run "An RTC alarm is armed or its state is unavailable"
before=$(s0i3_us)
[ -n "$before" ] || fail_run "S0I3 residency counter unavailable"
tail=$(journalctl -b -k -n 1 -o cat --show-cursor --no-pager) ||
    fail_run "Cannot establish a kernel journal cursor"
cursor=$(printf '%s\n' "$tail" | sed -n 's/^-- cursor: //p')
[ -n "$cursor" ] || fail_run "No current kernel journal cursor"

alarm=''
sleep_queued=0
clear_own_alarm()
{
    # A queued request can still suspend after we exit. In that case
    # retain the alarm even on interrupt or ambiguous journal evidence.
    [ "$sleep_queued" -eq 0 ] || return 0
    current=$(cat "$rtc/wakealarm") || return
    if [ -n "$alarm" ] && [ "$current" = "$alarm" ]; then
        rtcwake -d /dev/rtc0 -m disable >/dev/null
    fi
}
trap clear_own_alarm EXIT
trap 'exit 1' HUP INT TERM

printf 'INFO S0I3 before: %sus\n' "$before"
printf 'INFO suspending for %ss with RTC wake\n' "$seconds"
check_no_alarm || fail_run "RTC alarm state changed before arming"
rtc_before=$(rtc_event_count) || fail_run "Cannot read the RTC fixed-event counter"
rtcwake -d /dev/rtc0 -m no -s "$seconds"
alarm=$(cat "$rtc/wakealarm")
case "$alarm" in ''|*[!0-9]*) fail_run "RTC alarm could not be verified";; esac
check_no_sleep_inhibitor || fail_run "Suspend became inhibited before the request"
[ "$(cat "$rtc/wakealarm")" = "$alarm" ] &&
[ "$(cat "$rtc/since_epoch")" -lt "$alarm" ] ||
    fail_run "RTC alarm was replaced or elapsed before requesting suspend"
sleep_queued=1
systemctl --check-inhibitors=yes suspend || fail_run "Suspend request not confirmed; leaving RTC alarm intact"

state=pending
tries=0
while [ "$tries" -lt 45 ]; do
    resume_log=$(journalctl -b -k --after-cursor="$cursor" -o cat --no-pager) ||
        fail_run "Cannot read the suspend journal; leaving RTC alarm intact"
    state=$(printf '%s\n' "$resume_log" | awk '
        /^PM: suspend entry \(s2idle\)$/ {
            if (entry || exit_seen) bad = 1
            entry = 1
        }
        /^PM: suspend exit$/ {
            if (!entry || exit_seen) bad = 1
            exit_seen = 1
        }
        END {
            if (bad) print "invalid"
            else if (entry && exit_seen) print "resumed"
            else print "pending"
        }')
    case "$state" in
        resumed) break ;;
        invalid) fail_run "Ambiguous suspend journal; leaving RTC alarm intact" ;;
    esac
    tries=$((tries + 1))
    sleep 1
done
[ "$state" = resumed ] || fail_run "No complete suspend cycle; leaving RTC alarm intact"
sleep_queued=0
# RTC wakes on IRQ 9, shared by ACPI SCI and the INT0002 PME handler.
rtc_now=$(cat "$rtc/since_epoch")
rtc_after=$(rtc_event_count) || fail_run "Cannot read the RTC fixed-event counter after resume"
wake_irq=$(cat "$irq")
expected_alarm=$alarm
clear_own_alarm
alarm=''
after=$(s0i3_us)
[ -n "$after" ] || fail_run "S0I3 residency counter unavailable after resume"
delta=$((after - before))
printf 'INFO S0I3 after:  %sus\n' "$after"
printf 'INFO S0I3 delta:  %sus\n' "$delta"
printf 'INFO wake IRQ: %s; RTC fixed-event count: %s -> %s\n' "$wake_irq" "$rtc_before" "$rtc_after"
[ "$wake_irq" = 9 ] && [ "$rtc_now" -ge "$expected_alarm" ] &&
[ "$((rtc_after - rtc_before))" -eq 1 ] ||
    fail_run "Suspend ended without corroborating evidence of an RTC wake"
if printf '%s\n' "$resume_log" | grep -Eq '^ACPI: PM: (ACPI custom handler wakeup|ACPI non-EC GPE wakeup|Wakeup after ACPI Notify sync|Wakeup unrelated to ACPI SCI)$'; then
    fail_run "Kernel reported a different wake source"
fi

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

resume_log=$(journalctl -b -k --after-cursor="$cursor" -o cat --no-pager) ||
    fail_run "Cannot verify kernel messages after resume"
if printf '%s\n' "$resume_log" | grep -Eqi     'DSP subsystem start timed out|DSP power-up timed out|warm DSP resume failed.*forcing cold restart.*(failed|timeout)'; then
    printf 'MISS TFA DSP resume error detected\n'
    printf '%s\n' "$resume_log" | grep -Ei         'tfa98|DSP subsystem start timed out|DSP power-up timed out|warm DSP resume failed' | tail -n 80
    fail=1
else
    printf 'OK   no TFA DSP resume timeout detected\n'
fi

exit "$fail"
