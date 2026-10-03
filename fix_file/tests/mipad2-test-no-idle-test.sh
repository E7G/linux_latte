#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Host test for the no-idle status preflight; no system settings are changed.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
helper=${1:-"$script_dir/../packages/mipad2-test-no-idle/src/mp2-test-no-idle"}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp/bin"

cat > "$tmp/bin/id" <<'EOF'
#!/bin/sh
if [ "${1:-}" = -u ]; then
    if [ "${2:-}" = user ]; then
        echo 1000
    else
        echo 0
    fi
    exit 0
fi
exec /usr/bin/id "$@"
EOF

cat > "$tmp/bin/runuser" <<'EOF'
#!/bin/sh
while [ "$#" -gt 0 ]; do
    if [ "$1" = gsettings ]; then
        shift
        exec gsettings "$@"
    fi
    shift
done
exit 2
EOF

cat > "$tmp/bin/systemctl" <<'EOF'
#!/bin/sh
[ "${1:-}" = is-active ] || exit 2
case "${MOCK_SERVICE_STATE:-active}" in
    active) echo active; exit 0 ;;
    *) echo inactive; exit 3 ;;
esac
EOF

cat > "$tmp/bin/gsettings" <<'EOF'
#!/bin/sh
[ "${1:-}" = get ] || exit 2
case "${3:-}" in
    idle-delay) printf '%s\n' "${MOCK_IDLE_DELAY:-uint32 0}" ;;
    idle-dim) printf '%s\n' "${MOCK_IDLE_DIM:-false}" ;;
    sleep-inactive-ac-type) printf '%s\n' "${MOCK_SLEEP_AC:-'nothing'}" ;;
    sleep-inactive-battery-type) printf '%s\n' "${MOCK_SLEEP_BATTERY:-'nothing'}" ;;
    *) exit 2 ;;
esac
EOF
chmod +x "$tmp/bin/id" "$tmp/bin/runuser" "$tmp/bin/systemctl" "$tmp/bin/gsettings"

if ! env PATH="$tmp/bin:/usr/bin:/bin" MOCK_SERVICE_STATE=active \
    /bin/sh "$helper" status > "$tmp/active"; then
    cat "$tmp/active" >&2
    echo "FAIL expected active settings to pass status" >&2
    exit 1
fi
grep -q 'PASS anti-idle inhibitor active' "$tmp/active"

if env PATH="$tmp/bin:/usr/bin:/bin" MOCK_SERVICE_STATE=inactive \
    /bin/sh "$helper" status > "$tmp/inactive" 2>&1; then
    echo "FAIL inactive inhibitor passed status" >&2
    exit 1
fi
if env PATH="$tmp/bin:/usr/bin:/bin" MOCK_SERVICE_STATE=active \
    MOCK_IDLE_DELAY='uint32 300' /bin/sh "$helper" status \
    > "$tmp/misconfigured" 2>&1; then
    echo "FAIL nonzero idle delay passed status" >&2
    exit 1
fi

echo "PASS no-idle status accepts only active inhibitor and disabled GNOME idle/sleep"
