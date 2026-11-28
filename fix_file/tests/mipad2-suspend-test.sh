#!/bin/sh
# Active Mi Pad 2 s2idle/S0ix regression test.
# This deliberately suspends the tablet and uses RTC wakeup.
set -eu

fail_run()
{
    printf 'MISS %s\n' "$*" >&2
    exit 1
}

mode=normal
case "${1:-}" in
    --preflight) mode=preflight; shift; [ "$#" -eq 0 ] || fail_run "Usage: $0 --preflight" ;;
    --capture) mode=capture; shift ;;
esac
seconds=${1:-8}
[ "$#" -le 1 ] || fail_run "Usage: $0 [--capture] [seconds: 3-300], or --preflight"
case "$seconds" in
    [1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;;
    *) fail_run "Usage: $0 [seconds: 3-300]" ;;
esac
[ "$seconds" -ge 3 ] && [ "$seconds" -le 300 ] ||
    fail_run "Suspend duration must be 3-300 seconds"
if [ "$(id -u)" -ne 0 ]; then
    case "$mode" in
        preflight) exec sudo /bin/sh "$0" --preflight ;;
        capture) exec sudo /bin/sh "$0" --capture "$seconds" ;;
        *) exec sudo /bin/sh "$0" "$seconds" ;;
    esac
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
if [ "$mode" != preflight ]; then
    exec 9>>/run/mipad2-suspend-test.lock
    flock -n 9 || fail_run "Another Mi Pad 2 suspend test is active"
fi

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

# pmc_atom reads u32 registers and displays ticks shifted by 5.
# Keep the kernel's reported units; all five counters have this period.
pmc_period_us=137438953472

boottime_us()
{
    # The first field of /proc/uptime includes time spent suspended.
    LC_ALL=C awk '
        NR == 1 && $1 ~ /^[0-9]+[.][0-9][0-9]$/ {
            split($1, time, "[.]")
            if (time[1] <= 999999999) {
                printf "%.0f\n", time[1] * 1000000 + time[2] * 10000
                valid = 1
            }
        }
        END { if (!valid) exit 1 }
    ' /proc/uptime
}

pmc_snapshot()
{
    # Bracket the debugfs read, so bounded read latency is not residency.
    lo=$(boottime_us) || return 1
    counters=$(LC_ALL=C awk -v period="$pmc_period_us" '
        BEGIN {
            n = split("S0IR S0I1 S0I2 S0I3 S0", keys, " ")
            for (i = 1; i <= n; i++)
                expected[keys[i]] = 1
        }
        $1 in expected {
            if (++seen[$1] != 1 || NF != 3 || $2 != "Residency:" ||
                $3 !~ /^[0-9]+us$/) {
                invalid = 1
                next
            }
            v = $3
            sub(/us$/, "", v)
            v += 0
            if (v >= period || v % 32 != 0) invalid = 1
            value[$1] = v
        }
        END {
            if (invalid) exit 1
            for (i = 1; i <= n; i++)
                if (!seen[keys[i]]) exit 1
            for (i = 1; i <= n; i++)
                printf "%.0f%s", value[keys[i]], i == n ? "\n" : " "
        }
    ' "$pmc") || return 1
    hi=$(boottime_us) || return 1
    [ "$hi" -ge "$lo" ] || return 1
    printf '%s %s %s\n' "$lo" "$hi" "$counters"
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

pme_irq_snapshot()
{
    # ACPI SCI and the virtual GPIO controller share IRQ 9. Compare its
    # pin-2 child, including the IRQ number and CPU columns, across the test.
    awk '
        NR == 1 {
            if (!NF) {
                invalid = 1
                exit
            }
            for (i = 1; i <= NF; i++) {
                if ($i !~ /^CPU[0-9]+$/) {
                    invalid = 1
                    exit
                }
                cpus = cpus (i == 1 ? "" : ",") $i
            }
            columns = NF
            next
        }
        /[[:space:]]INT0002 Virtual GPIO[[:space:]]+2[[:space:]]+ACPI:Event[[:space:]]*$/ {
            if (++matches != 1 || $1 !~ /^[0-9]+:$/ || NF != columns + 6) {
                invalid = 1
                exit
            }
            irq = $1
            for (i = 2; i <= columns + 1; i++) {
                if ($i !~ /^[0-9]+$/) {
                    invalid = 1
                    exit
                }
                counts = counts (i == 2 ? "" : ",") $i
            }
        }
        END {
            if (invalid || !columns) exit 1
            if (matches) printf "%s%s:%s\n", irq, cpus, counts
            else print "unavailable"
        }
    ' /proc/interrupts
}

if [ "$mode" = preflight ]; then
    check_no_alarm || fail_run "An RTC alarm is armed or its state is unavailable"
    pmc_snapshot >/dev/null || fail_run "Invalid PMC residency snapshot"
    rtc_event_count >/dev/null || fail_run "Cannot read the RTC fixed-event counter"
    pme=$(pme_irq_snapshot) || fail_run "Cannot read virtual PME interrupt counters"
    [ "$pme" != unavailable ] || fail_run "Virtual PME child interrupt is unavailable"
    printf 'OK   PMC residency, RTC fixed-event counter and separate PME child are readable\n'
    trace=/sys/kernel/tracing
    if [ -r "$trace/events/pmc_atom/pmc_atom_s2idle/format" ] &&
       [ -r "$trace/events/power/suspend_resume/format" ]; then
        printf 'INFO PMC trace events present in tracefs\n'
    else
        printf 'INFO PMC trace events unavailable in the current tracefs\n'
    fi
    check_no_sleep_inhibitor || fail_run "Cannot confirm suspend is allowed"
    printf 'OK   read-only preflight passed; no suspend requested\n'
    exit 0
fi
check_no_sleep_inhibitor || fail_run "Cannot confirm suspend is allowed"
check_no_alarm || fail_run "An RTC alarm is armed or its state is unavailable"
before=$(pmc_snapshot) || fail_run "Invalid PMC residency snapshot before suspend"
read -r before_lo before_hi before_ir before_i1 before_i2 before_i3 before_s0 <<EOF
$before
EOF
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
capture_dir=''
instance=''
trace_saved=0

capture_finish()
{
    rc=$?
    trap - EXIT HUP INT TERM
    clear_own_alarm || rc=1
    if [ -n "$instance" ]; then
        printf '0\n' > "$instance/tracing_on" || rc=1
        if [ "$trace_saved" -eq 0 ]; then
            # Never invent the end marker when the cycle is still uncertain.
            cat "$instance/trace" > "$capture_dir/pmc.trace" || rc=1
        fi
        for event in "$pmc_event" "$power_event"; do
            if [ -e "$instance/$event/enable" ]; then
                printf '0\n' > "$instance/$event/enable" || rc=1
            fi
        done
        rmdir "$instance" || rc=1
    fi
    if [ -n "$capture_dir" ]; then
        printf 'PMC_CAPTURE_DIR=%s\n' "$capture_dir" >&7
    fi
    exit "$rc"
}

capture_start()
{
    trace=/sys/kernel/tracing
    pmc_event=events/pmc_atom/pmc_atom_s2idle
    power_event=events/power/suspend_resume
    [ -d "$trace/instances" ] && [ -r "$trace/$power_event/format" ] &&
    [ -r "$trace/$pmc_event/format" ] && [ "$(cat "$trace/$pmc_event/enable")" = 0 ] ||
        fail_run "Expected an available, globally disabled PMC trace event"
    capture_id=$(tr -d '\n-' < /proc/sys/kernel/random/uuid)
    [ "${#capture_id}" -eq 32 ] || fail_run "Invalid trace capture ID"
    case "$capture_id" in *[!0-9a-f]*) fail_run "Invalid trace capture ID" ;; esac
    exec 7>&1
    capture_dir=$(mktemp -d /run/mipad2-pmc-capture.XXXXXXXX)
    exec > "$capture_dir/rtc.log" 2>&1
    path="$trace/instances/mipad2-pmc-$capture_id"
    mkdir "$path" || fail_run "Cannot allocate a fresh tracefs instance"
    instance=$path
    printf '0\n' > "$instance/tracing_on"
    printf 'global\n' > "$instance/trace_clock"
    printf '1\n' > "$instance/$pmc_event/enable"
    printf '1\n' > "$instance/$power_event/enable"
    printf '1\n' > "$instance/tracing_on"
    printf 'mipad2-pmc:%s:begin\n' "$capture_id" > "$instance/trace_marker"
    printf 'INFO PMC trace capture: %s\n' "$capture_id"
}

trap capture_finish EXIT
trap 'exit 1' HUP INT TERM

printf 'INFO S0I3 before: %sus\n' "$before_i3"
printf 'INFO suspending for %ss with RTC wake\n' "$seconds"
check_no_alarm || fail_run "RTC alarm state changed before arming"
rtc_before=$(rtc_event_count) || fail_run "Cannot read the RTC fixed-event counter"
pme_before=$(pme_irq_snapshot) || fail_run "Cannot read virtual PME interrupt counters"
[ "$pme_before" != unavailable ] || fail_run "Virtual PME child interrupt is unavailable"
if [ "$mode" = capture ]; then
    capture_start
    check_no_sleep_inhibitor || fail_run "Suspend became inhibited during trace setup"
    check_no_alarm || fail_run "RTC alarm state changed during trace setup"
fi
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
if [ -n "$instance" ]; then
    printf 'mipad2-pmc:%s:end\n' "$capture_id" > "$instance/trace_marker"
    printf '0\n' > "$instance/tracing_on"
    cat "$instance/trace" > "$capture_dir/pmc.trace"
    trace_saved=1
fi
# RTC wakes on IRQ 9, shared by ACPI SCI and the INT0002 PME handler.
rtc_now=$(cat "$rtc/since_epoch")
rtc_after=$(rtc_event_count) || fail_run "Cannot read the RTC fixed-event counter after resume"
wake_irq=$(cat "$irq")
expected_alarm=$alarm
clear_own_alarm
alarm=''
after=$(pmc_snapshot) || fail_run "Invalid PMC residency snapshot after resume"
read -r after_lo after_hi after_ir after_i1 after_i2 after_i3 after_s0 <<EOF
$after
EOF
[ "$after_lo" -ge "$before_hi" ] ||
    fail_run "Boot-time clock moved backwards between PMC samples"
elapsed=$((after_hi - before_lo))
# PMC time is nominal and can run ahead of the boot-time clock. Permit
# 10% rate difference and 100 ms for timestamp granularity and skew.
# A window that permits a full counter period makes the delta ambiguous.
limit=$((elapsed + elapsed / 10 + 100000))
[ "$limit" -lt "$pmc_period_us" ] ||
    fail_run "PMC sampling interval does not exclude a full counter period"
printf 'INFO PMC sample window: %sus (per-counter limit %sus)\n' "$elapsed" "$limit"

invalid=
for state in S0IR S0I1 S0I2 S0I3 S0; do
    case "$state" in
        S0IR) a=$after_ir; b=$before_ir ;;
        S0I1) a=$after_i1; b=$before_i1 ;;
        S0I2) a=$after_i2; b=$before_i2 ;;
        S0I3) a=$after_i3; b=$before_i3 ;;
        S0)   a=$after_s0; b=$before_s0 ;;
    esac
    d=$(((a - b + pmc_period_us) % pmc_period_us))
    if [ "$a" -lt "$b" ]; then
        wrapped=' (modulo counter period)'
    else
        wrapped=''
    fi
    printf 'INFO %s delta:  %sus%s (before %sus, after %sus)\n' "$state" "$d" "$wrapped" "$b" "$a"
    if [ "$d" -gt "$limit" ]; then
        invalid="$invalid $state"
    fi
    if [ "$state" = S0I3 ]; then
        delta=$d
    fi
done
printf 'INFO wake IRQ: %s; RTC fixed-event count: %s -> %s\n' "$wake_irq" "$rtc_before" "$rtc_after"
pme_after=$(pme_irq_snapshot) || fail_run "Cannot read virtual PME interrupt counters after resume"
printf 'INFO virtual PME child IRQ snapshot: %s -> %s\n' "$pme_before" "$pme_after"
[ "$wake_irq" = 9 ] && [ "$rtc_now" -ge "$expected_alarm" ] &&
[ "$((rtc_after - rtc_before))" -eq 1 ] ||
    fail_run "Suspend ended without corroborating evidence of an RTC wake"
if printf '%s\n' "$resume_log" | grep -Eq '^ACPI: PM: (ACPI custom handler wakeup|ACPI non-EC GPE wakeup|Wakeup after ACPI Notify sync|Wakeup unrelated to ACPI SCI)$'; then
    fail_run "Kernel reported a different wake source"
fi

[ "$pme_before" = "$pme_after" ] ||
    fail_run "Virtual PME child interrupt evidence changed during the RTC test"

[ -z "$invalid" ] ||
    fail_run "PMC residency deltas exceed the measured boot-time window:$invalid"

# Allow for entry/exit latency but require most of the requested interval in S0i3.
minimum=$((seconds * 700000))
fail=0
if [ "$delta" -ge "$minimum" ]; then
    printf 'OK   S0I3 residency increased sufficiently\n'
else
    printf 'MISS S0I3 residency increased only %sus (minimum %sus)\n' "$delta" "$minimum"
    fail=1
fi

if [ "$mode" = capture ]; then
    printf 'INFO physical media smoke not run in capture mode\n'
elif command -v mipad2-hardware-smoke >/dev/null 2>&1; then
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
