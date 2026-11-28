# Mi Pad 2 7.2 RT5659 machine-link identity

The factory Windows Realtek INF identifies ACPI hardware ID 10EC5659.
[Xiaomi Android's machine driver](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/78fbd35b6c73ee51129d690c4306f320e40a1401/sound/soc/intel/board/cht_bl_dpcm_rt5659.c#L890-L900)
names the I2C instance :00, while the current Linux firmware path
was hardcoded as :01. Those suffixes are not the hardware identity.

Use the same physical I2C resolver when attaching the board properties
and when binding ASoC. On Mi Pad 2 firmware with the existing RTK3
namespace path, that path selects the physical device irrespective of
its enumeration suffix. If the path is absent, accept a unique live
I2C client with the exact ACPI ID, not a substring of a device name.
Do not take the first of two ambiguous candidates. If the preferred
client has not been enumerated, the ASoC probe defers.

Use that one device in both SSP-to-AIF1 and AIF2-to-amplifier links,
including the AIF2 CPU-side component identity. The latter is a
direct codec-to-codec path: it must keep zero PCM platforms, even
when machine data overrides the SST/SOF platform. The old global
platform-name fixup rejected a non-NULL override at that link.
Per-probe card/links and mutable component data avoid leaving stale
names or SSP0 choices behind across reprobes.

Tests compile the actual resolver, the board's owned node callbacks,
and the machine's DAI template and link configuration. They cover
:00/:01, two possible clients with and without a preferred handle,
missing client, both SSP selections, custom/default DSP names and
both amplifiers remaining on the platform-less AIF2 link. Their
scope is binding and configuration, not real playback, jack detection
or Windows/Android firmware boot on a tablet. No PCM labels, gains,
clocking, GPIOs or vendor DSP parameters are changed.
