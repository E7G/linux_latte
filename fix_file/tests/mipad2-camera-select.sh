#!/bin/sh
# Select the camera exposed by the single legacy AtomISP video node.
set -eu

case "${1:-}" in
	front|rear) wanted=$1 ;;
	*) printf 'usage: %s front|rear [video-node]\n' "$0" >&2; exit 2 ;;
esac

video_node=${2:-}
if [ -z "$video_node" ]; then
	for node in /dev/video*; do
		[ -c "$node" ] || continue
		if v4l2-ctl -d "$node" --list-inputs 2>&1 | grep -Eiq 'ov5693|t4ka3'; then
			video_node=$node
			break
		fi
	done
fi

[ -n "$video_node" ] || { echo 'AtomISP video node not found' >&2; exit 1; }
inputs=$(v4l2-ctl -d "$video_node" --list-inputs 2>&1 || true)
case "$wanted" in
	front) pattern='ov5693' ;;
	rear) pattern='t4ka3' ;;
esac
input=$(printf '%s\n' "$inputs" | awk -v pattern="$pattern" '$1 == "Input" { id=$3 } tolower($0) ~ pattern { print id; exit }')
[ -n "$input" ] || { printf '%s camera input not found\n' "$wanted" >&2; exit 1; }
v4l2-ctl -d "$video_node" --set-input="$input"
printf 'Selected %s camera on %s (input %s)\n' "$wanted" "$video_node" "$input"
