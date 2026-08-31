#!/bin/sh
# Capture one frame from both Mi Pad 2 cameras through the legacy AtomISP node.
# Keep format setup and streaming in the same v4l2-ctl invocation.
set -u

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
	if v4l2-ctl -d "$video_node" --set-input="$input" --set-fmt-video=width=1280,height=720,pixelformat=YU12 --stream-mmap --stream-count=1 --stream-to="$out" >"$log" 2>&1 && size=$(wc -c <"$out") && [ "$size" -gt 0 ]; then
		printf 'OK   %s capture (%s bytes)\n' "$label" "$size"
	else
		printf 'MISS %s capture\n' "$label"
		cat "$log"
		fail=1
	fi
	rm -f "$out" "$log"
}

# Exercise the rear sensor first; on this platform the AtomISP power/CSI
# transition is reliable in this order after a cold boot.
if [ -n "$rear_input" ]; then capture_one rear "$rear_input"; else printf 'MISS T4KA3 input\n'; fail=1; fi
if [ -n "$front_input" ]; then capture_one front "$front_input"; else printf 'MISS OV5693 input\n'; fail=1; fi
exit "$fail"
