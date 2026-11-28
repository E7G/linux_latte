# Mi Pad 2 7.2 RT5659 board properties

The factory Windows Realtek I2S Audio Codec INF (6.2.9600.4366)
matches the ACPI hardware ID 10EC5659. Xiaomi's
[Android codec driver](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/78fbd35b6c73ee51129d690c4306f320e40a1401/sound/soc/codecs/rt5659.c#L4374-L4379)
uses the same ID, and its
[Mi Pad 2 machine driver](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/78fbd35b6c73ee51129d690c4306f320e40a1401/sound/soc/intel/board/cht_bl_dpcm_rt5659.c#L890-L900)
connects that codec to SSP2. Use the firmware ID rather than a substring
of the Linux-generated device name to find the existing I2C client.

The Linux board quirk supplies missing jack-source, LDO and reset
properties as a secondary software node. Attach it using the driver
core API and release it with the board's managed resources, before
the GPIO software nodes are released. Only the installed board node is
removed; an existing or replacement node is preserved. Missing
codec or property-attachment failure is reported without inhibiting
FTSC1000, the discrete amplifiers, or the indicator LED.

No GPIO wiring, polarity, jack mode, PCM route, amplifier setting,
or power sequence changes. The modeled host test uses the production
identity/attach/cleanup functions; it covers normal teardown, an
existing or replaced node, missing firmware/client, and failures at each
ownership step. It does not prove physical audio playback or headset
detection. This change does not forcibly unbind an already-probed codec.
