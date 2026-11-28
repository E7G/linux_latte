# Mi Pad 2 7.2: ACPI touchscreen and DMI fallback

The factory Windows FocalTech INF binds the I2C-HID controller through
ACPI\FTSC1000. The 7.2 board code explains why the same node can also be
hidden by firmware: its _STA depends on TCPL. Linux needs both paths: use
the already-enumerated ACPI client when present, or create the DMI client
on I2C6 at 0x38 using that board's IRQ if the node is absent.

The duplicate check formerly came after the fallback IRQ request. Even
a duplicate could request an ACPI-owned GPIO, reconfigure its trigger,
or abort the board fallback before later entries (e.g. TFA9890 audio and
KTD2026 LED) were considered. Resolve the adapter and check ownership
before acquiring the fallback IRQ. The GPIO number, reset polarity,
timing, IRQ flags and I2C addresses are unchanged.

The modeled host test compiles the production match and instantiate
functions. It covers ACPI and PCI adapter lookup; an enumerated FTSC1000
whose fallback IRQ is unavailable; continuation to the next board
child; same address on another bus or different address on the same
bus; absent ACPI client; and balanced references when IRQ, adapter or
client creation fails. It does not simulate firmware, GPIO thresholds
or an actual touchscreen gesture.
