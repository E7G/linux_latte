#!/bin/sh
# Capture one frame from a Mi Pad 2 camera through the legacy AtomISP node.
# Keep format setup and streaming in the same v4l2-ctl invocation.
set -u

target=${1:-both}
case "$target" in
	front|rear|both) ;;
	-h|--help)
		printf 'Usage: %s [front|rear|both]\n' "$0"
		exit 0
		;;
	*)
		printf 'Usage: %s [front|rear|both]\n' "$0" >&2
		exit 2
		;;
esac

fail=0
video_node=
for node in /dev/video*; do
	[ -c "$node" ] || continue
	if v4l2-ctl -d "$node" --list-inputs 2>&1 | grep -Eiq 'ov5693|t4ka3'; then
		video_node=$node
		break
	fi
done

if [ -z "$video_node" ]; then
	printf 'MISS AtomISP video node with OV5693/T4KA3 inputs\n'
	exit 1
fi
printf 'OK   camera node %s\n' "$video_node"

inputs=$(v4l2-ctl -d "$video_node" --list-inputs 2>&1 || true)
front_input=$(printf '%s\n' "$inputs" | awk '$1 == "Input" { id=$3 } tolower($0) ~ /ov5693/ { print id; exit }')
rear_input=$(printf '%s\n' "$inputs" | awk '$1 == "Input" { id=$3 } tolower($0) ~ /t4ka3/ { print id; exit }')

capture_one()
{
	label=$1
	input=$2
	out=$(mktemp)
	log=$(mktemp)
	if timeout --signal=TERM --kill-after=2s 15s \
		v4l2-ctl -d "$video_node" --set-input="$input" \
		--set-fmt-video=width=1280,height=720,pixelformat=YU12 \
		--stream-mmap --stream-count=1 --stream-to="$out" >"$log" 2>&1 \
		&& size=$(wc -c <"$out") && [ "$size" -gt 0 ]; then
		printf 'OK   %s capture (%s bytes)\n' "$label" "$size"
	else
		printf 'MISS %s capture\n' "$label"
		cat "$log"
		fail=1
	fi
	rm -f "$out" "$log"
}

capture_target()
{
	label=$1
	input=$2
	if [ -n "$input" ]; then
		capture_one "$label" "$input"
	else
		printf 'MISS %s input\n' "$label"
		fail=1
	fi
}

# The AtomISP transition can wedge on some firmware revisions.  Allow a
# single-camera run for recovery/debugging, and do not switch to the second
# sensor after a failed capture.
case "$target" in
	rear) capture_target rear "$rear_input" ;;
	front) capture_target front "$front_input" ;;
	both)
		capture_target rear "$rear_input"
	[ "$fail" -eq 0 ] && capture_target front "$front_input"
		;;
esac
exit "$fail"
