#!/bin/sh
# Static cross-check of the Mi Pad 2 stereo UCM routes and kernel declarations.
# This does not prove that either speaker emits sound on physical hardware.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

ucm=fix_file/packages/mipad2-alsa-ucm/src/cht-bsw-rt5659
codec=sound/soc/codecs/tfa989x.c
board=sound/soc/intel/boards/cht_bsw_rt5659.c
for f in "$ucm/cht-bsw-rt5659.conf" "$ucm/HiFi.conf" "$codec" "$board"; do
    test -s "$f" || { echo "missing audio route input: $f" >&2; exit 1; }
done

grep -Fq 'SectionUseCase."HiFi"' "$ucm/cht-bsw-rt5659.conf"
grep -Fq 'File "HiFi.conf"' "$ucm/cht-bsw-rt5659.conf"
grep -Fq 'SOC_DAPM_ENUM("Amp Input", chsa_enum)' "$codec"
grep -Fq 'SOC_DAPM_ENUM("Amp Input1", chsa_enum)' "$codec"
grep -Fq '{"Amp Input", "Left", "AIFINL"}' "$codec"
grep -Fq '{"Amp Input1", "Right", "AIFINR"}' "$codec"
grep -Fq 'COMP_CODEC("i2c-tfa9890:00"' "$board"
grep -Fq 'COMP_CODEC("i2c-tfa9890:01"' "$board"
grep -Fq "Amp Input' Left" "$ucm/HiFi.conf"
grep -Fq "Amp Input1' Right" "$ucm/HiFi.conf"
grep -Fq 'PlaybackChannels 2' "$ucm/HiFi.conf"
grep -Fq 'Headphones' "$ucm/HiFi.conf"
grep -Fq 'IntMic' "$ucm/HiFi.conf"
grep -Fq 'HeadsetMic' "$ucm/HiFi.conf"

echo "PASS: UCM declares distinct left/right TFA989x routes and expected audio devices."
echo "NOTE: static checks do not prove audible speaker, headset, or microphone function."
