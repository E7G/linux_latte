# Known issues / 当前已知限制

本文档只记录与当前 `cachyos-mipad2` 分支和 `xiaomipad2_defconfig` 相符的已知限制。这里的“已集成”表示代码、配置或辅助工具已经存在，**不等于该功能已经在所有发行版和所有使用场景下完全稳定**。

## 1. AtomISP 摄像头仍是实验性功能

当前树已经包含 OV5693 前摄、T4KA3 后摄、DW9761 兼容对焦、Mi Pad 2 AtomISP bridge、1280×720 保守默认格式、frame-interval 处理以及近期的 AtomISP 内存分配健壮性修复。

2026-09-25 真机回归已经确认：

- OV5693 前摄和 T4KA3 后摄都能通过 `/dev/video0` 完成 mmap 短流采集；
- 连续 6 次前/后摄交替切换和采集通过；
- DW9719 对焦控制正常暴露 `focus_absolute=0..1023`；
- `v4l2-ctl` 可能打印 `VIDIOC_CREATE_BUFS: Inappropriate ioctl for device`，但当前 AtomISP mmap 路径仍会成功采集并返回 0，因此这条消息本身不能当作采集失败。

当前剩余风险主要变成：

- 某些 V4L2 应用仍可能因为格式协商或旧 AtomISP ioctl 差异而不兼容；
- 前后摄白平衡/3A tuning 仍需继续校准，当前偏绿问题不是 Bayer order 错误；
- 后摄 AF helper 已在真机完成重复快速/完整扫描；近/远目标锐度仍需对照图验证；
- 2026-09-26 正式稳定内核已通过一次 8 秒 S0i3 suspend/resume，唤醒后前/后摄采集和连续 6 次切换再次通过；后续媒体/电源改动后仍应重复该回归。

优先使用仓库提供的测试脚本：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

不要仅凭 `/dev/video*` 能枚举就认定摄像头已经完全正常。

## 2. AtomISP 固件路径有新旧兼容逻辑

当前 AtomISP 代码首先请求：

```text
intel/ipu/shisp_2401a0_v21.bin
```

失败后才回退到旧顶层文件名：

```text
shisp_2401a0_v21.bin
```

新安装推荐使用 `mipad2-camera-support`，它会安装到：

```text
/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin
```

若发行版的 `/lib/firmware` 与 `/usr/lib/firmware` 不是同一固件目录，请按该发行版的 firmware loader 布局调整，并以 `dmesg` 中实际请求的路径为准。

## 3. Suspend / resume 仍需持续回归

当前固件只对 Linux 暴露 `[s2idle]`，但这不等价于“缺少低功耗休眠”。Cherry Trail 的当前 6.14 `pmc_atom` 已注册 s2idle/S0ix 检查，并提供 S0I1/S0I2/S0I3 residency；真机 CPU idle 也已经确认 C6/C7/C7S 都在累计。2026-09-26 在正式 `6.14.0-mipad2-cachyos-navkeys` 上用 RTC 做 8 秒 suspend，S0I3 residency 增加约 7.43 秒（约 93%），唤醒后 Wi-Fi/SSH 自动恢复，USB gadget、RT5659/TFA9890 和摄像头回归均通过。正确验收目标仍然是确认系统实际进入 S0i3，而不是强行制造一个 `deep` 选项。

仍不能把 suspend/resume 视为所有外设都已完全稳定。每次修改 ACPI、电源管理、音频、无线、IIO 或媒体代码后，至少重新检查：

- Wi-Fi / Bluetooth 是否恢复；
- RT5659/TFA9890 音频是否仍可播放和录音；
- IIO 传感器节点和数据是否恢复；
- 摄像头在 resume 后是否仍可完成采集；
- USB gadget / UDC 是否仍可工作。

建议 resume 后运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

注意 smoke test 主要验证设备枚举和接口存在性，不能替代实际播放、录音、传感器数据和摄像头采集测试。

## 4. USB gadget 依赖固件暴露可用 UDC

内核 defconfig 已启用 DWC3 PCI dual-role、USB Gadget、ConfigFS ACM 和 gadget serial console 支持，但某些 Mi Pad 2 固件设置仍可能让 `/sys/class/udc/` 为空。

在修改 BIOS/UEFI 变量前先检查：

```bash
ls -la /sys/class/udc/
dmesg | grep -Ei 'dwc3|udc|gadget|usb'
```

只有确认确实是固件 OTG 模式问题后，再参考 `fix_file/USB_OTG_Gadget.md`。其中 Setup 偏移属于历史 Mi Pad 2 固件经验，不应套用到其他设备或未知 BIOS 版本。

## 5. 新旧 USB gadget 包互斥

当前推荐：

```text
mipad2-usb-serial
```

旧方案：

```text
mipad2-usb-gadget
```

`mipad2-usb-serial` 的 PKGBUILD 已声明 `conflicts` 和 `replaces` 旧包，因为同一个 UDC 不能同时被两套 gadget 配置占用。出现 `UDC busy` 时应优先排查旧服务/旧 gadget 是否仍在运行。

## 6. 无线功能仍依赖设备固件/NVRAM

内核中已有 BCM4356 的 `brcmfmac` 与 Broadcom HCI UART 配置，但这不意味着只装内核就一定能得到 Wi-Fi / Bluetooth。

当前仓库仍提供：

```text
fix_file/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt
fix_file/BCM4356A2.hcd
```

如果无线没有出现，应先检查 `dmesg` 中驱动实际请求的 firmware/NVRAM 文件名，而不是盲目重命名唯一副本。

## 7. Recovery 工具不是通用分区恢复器

当前 `mipad2-recovery` 只适用于项目当前假定的安装布局。尤其是 `mp2-recover` 目前把 Timeshift snapshot/restore device **硬编码为**：

```text
/dev/mmcblk0p2
```

而 `/boot` archive 的恢复会直接执行到当前 `/boot` 路径，脚本不会替你发现或挂载 boot 分区。

因此在恢复前必须确认：

```bash
findmnt /
findmnt /boot
```

与脚本假设一致。`mp2-backup` 已经会拒绝未挂载或非 VFAT 的 `/boot`，但这不意味着 `mp2-recover` 能自动适配不同分区布局。改过分区、root 设备或 boot 布局的安装不能直接使用默认恢复命令。

## 8. 当前 defconfig 不是 hardened / generic distro 配置

`xiaomipad2_defconfig` 是面向设备可用性和开发测试的配置。目前包括：

- `CONFIG_LTO_CLANG_THIN=y`；
- `CONFIG_CPU_MITIGATIONS=y` 默认启用；仅在受控性能对比中才可通过内核启动参数 `mitigations=off` 显式关闭；
- `CONFIG_VIRTUALIZATION` 未启用；
- 多个 Mi Pad 2 运行时组件采用模块形式。

CPU mitigations 默认启用，但该配置仍不是完整的发行版安全加固配置。`mitigations=off` 会关闭所有 CPU 漏洞缓解，仅应用于受控的性能对比。若改变工具链或 defconfig，记得检查最终 `.config`，不要仅根据 defconfig 文件推断最终编译配置。

## 9. BQ25890 充电上限已按原厂档案修正并通过真机验证

旧稳定内核使用 `linux,read-back-settings` 时，固件给 BQ25890 留下的 VREG 只有 4.208 V。真机曾出现约 4.165 V 时 charger 已报告 `Full`，但 BQ27520 仍只有 83%。

Android 原厂 Xiaomi 电池档案与真机 fuel gauge 一致：设计容量 6190 mAh、终止电流 256 mA、充电电压 4.400 V。当前稳定内核保留固件提供的其余充电电流、预充、温控和 OTG 参数，只针对 Mi Pad 2 覆盖 VREG 为 4.400 V。

2026-09-26 one-shot 和最终稳定内核验证结果：

- `constant_charge_voltage_max = 4400000`；
- `charge_term_current = 256000`；
- BQ27520 设计容量仍为 6190 mAh；
- 旧的 `Full@83%` 提前终止现象消失；
- 实测电量从 83% 继续充到 100%，满电附近电压约 4.35 V；
- 正式稳定内核在 USB 500 mA 输入下仍保持 4.400 V VREG。高负载时 battery 可能短暂显示 Discharging，这是系统负载高于当前 USB 输入限流的表现，不等同于 VREG 回退。

该路径已经进入 `cachyos-mipad2`，后续若修改充电器或 fuel-gauge 代码，应重新运行硬件 smoke test 并核对 VREG/ITERM/容量读数。

## 报告新问题

建议至少附带：

```bash
uname -a
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
dmesg > /tmp/mipad2-dmesg.txt
```

相机问题再附带：

```bash
media-ctl -p
v4l2-ctl --list-devices
```

并说明问题发生在冷启动、suspend/resume 后，还是某个外设已经使用过之后。

## 10. 2026-10-04 integrated 6.14 camera, sensor and resume audit

The local `codex/mipad2-6.14-integrated` branch was booted on the tablet as
`6.14.0-mipad2-cachyos`. The gated hardware smoke passed after boot and again
after RTC-timed s2idle/resume. OV5693 and T4KA3 each streamed three frames on
both checks; no camera module was hot-unloaded or rebound.

The branch's AtomISP `.vidioc_create_bufs = vb2_ioctl_create_bufs` path is now
runtime-verified: `VIDIOC_CREATE_BUFS` allocated two MMAP buffers for inputs 0
(OV5693) and 1 (T4KA3), both at 1280x720 YU12. The camera graph also exposes
the T4KA3 controls and DW9761 `focus_absolute` control.

The OV5693 NVMEM test passed on the branch module: 416-byte raw OTP, 320-byte
parsed OTP, CRC16/IBM `7bdf`, expected fixed AF block. The parsed calibration
SHA-256 was `23064aefd4419afe110edc218590dcce1b7b12b97f7d68db28ebacdb65c71b43`.

The T4KA3 raw NVMEM audit also passed on-device: 578 bytes; module/AF/LS1/LS2
checksums `112/103/112/229`; vendor `1`; factory AF range `237..366`; SHA-256
`18c2dc22c74d97570153864ac4f4273fe0463dff38ebdf9173a6e19b2c45859f`.
The new 544-byte calibrated NVMEM view mirrors Xiaomi Android's
[`dw9761_otp_format()`](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/cm-13.0/drivers/external_drivers/camera/drivers/media/i2c/micam/dw9761.c)
layout. A candidate T4KA3 module was built against the tablet's live 6.14
Clang/LTO configuration; the driver object also passed a `W=1` compile. Its
shared module-version CRCs matched the running kernel, and it was temporarily
loaded for an on-device byte-for-byte OTP test: 544 bytes, AF `237..366`, grid
`9x7`, CRC16/IBM `7e85`, SHA-256
`9d867793ff344619692df7f8dca65a70e6b3f508cfe90337db17f619f637772d`. The
stock module was restored immediately afterward. This validates OTP packing,
not image quality; the calibrated provider remains a source-tree change until
the branch is rebuilt and installed through its normal release path.

`mipad2-camera-af --fast` completed a live T4KA3 sweep using that OTP range and
returned `BEST focus=241`, score `0.00078127`, confidence `good`. A subsequent
full sweep repeated both macro-to-infinity passes and also selected focus `241`
(score `0.00104341`, confidence `good`). This verifies repeatable live
capture/focus control on the current scene; controlled near/far chart sharpness
and user-visible image review remain open. Lens was left at position `241`.

A read-only full hardware smoke passed again after the OTP/AF probes: Wi-Fi,
Bluetooth, RT5659, touch, DRM, eMMC, charger/fuel gauge, IIO sensors, USB UDC,
both camera endpoints and T4KA3/VCM controls were present; no known fatal driver
errors appeared in `dmesg`. The device currently advertises s2idle only.

The live front/rear images still need review on a known target under controlled
lighting. Green cast / 3A calibration remains open. The Windows OEM camera INFs
install sensor-specific CPF profiles (`OV5693_12P2BA535_{1,7}_CHT.cpf` and
`t4ka3_F8D02B_{1,2}_CHT.cpf`); the Linux AtomISP kernel tree has no CPF/AIQB
loader. The Android OV5693 driver instead exposes parsed factory OTP to the
camera stack through `g_priv_int_data`; this branch exposes the matching raw and
320-byte calibrated data as read-only NVMEM (verified against the tablet OTP).
The four Windows AIQB profiles contain four CMC matrices each: they are ISP
color/3A tuning, not sensor register tables. So the remaining green-cast fix
belongs in a compatible AtomISP userspace IQ/3A consumer, not guessed sensor
register writes. See the [Android OV5693 implementation](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/cm-13.0/drivers/external_drivers/camera/drivers/media/i2c/micam/ov5693.c#L1136-L1163).
The rear lens exports standard `focus_absolute` (0..1023); live AF now passes,
but target-based optical sharpness remains unverified.

## 11. IIO sensor orientation matrix

The integrated branch uses separate DMI-scoped matrices: accelerometer and
gravity `diag(1, 1, -1)`, gyro and magnetometer Android correction
`diag(-1, 1, -1)`. This split follows a 2026-10-04 device check: with the old
shared matrix, both physical landscape poses showed upside-down screen content
while `iio-sensor-proxy` reported the matching `left-up` / `right-up` labels.
Mutter maps those labels to opposite 90°/270° transforms
([source](https://github.com/GNOME/mutter/blob/main/src/backends/meta-orientation-manager.c#L1377-L1407));
flipping only accelerometer/gravity X swaps both landscape labels without
changing portrait or gyro/magnetometer data. The rebuilt one-shot 6.14 kernel
booted, the hardware smoke passed, and sysfs confirmed all three matrix values
and compass scale `0.000010000`. In the new build, physical right-landscape
reports `left-up` and physical left-landscape reports `right-up`; the user
confirmed the display is upright in both poses. Portrait tests report
`normal` (top edge up) and `bottom-up` (top edge down); the user confirmed the
upside-down physical pose displays correctly too. A live topology audit found
the standard accel/gyro IIO devices under HID `8086:0001` hub `.0002`, and the
magnetometer, inclinometer and device-rotation collections under hub `.0003`.

The tablet also exposes two `8086:0002` hubs (`.0004` and `.0005`), both bound
to `hid-sensor-hub`. Neither currently has a standard IIO child, but multiple
`HID-SENSOR-2000e1` children do bind to `hid_sensor_custom` and expose generic
`enable_sensor`, `input-*` and `feature-*` sysfs attributes. The saved Windows
INF identifies `HID\Vid_8086&Pid_0002` as `AdvSensorHIDClassDriverV2`; the
[USB HID Usage Tables](https://usb.org/sites/default/files/hut1_3_0.pdf)
define collection usage `0x20:0x00e1` as “Other: Custom”. The attribute names
and the serial/friendly-name feature reports reveal these eleven sensor types:

| LUID | Friendly name |
| --- | --- |
| `0211` | Lift Gesture Sensor |
| `0212` | Pan Zoom Gesture Sensor |
| `0230` | Step Counter Sensor |
| `0200` | Orientation AG Sensor |
| `0213` | Flick Gesture Sensor |
| `0232` | Physical Activity Sensor |
| `0237` | Instant Activity Sensor |
| `0205` | Simple Orientation Sensor |
| `0214` | Tilt Gesture Sensor |
| `0236` | Significant Motion Sensor |
| `0231` | Dead Reckoning Sensor |

All eleven reported `enable_sensor=0` before sampling. A reversible probe of
LUID `0205` enabled it through the generic sysfs control, read sensor state,
event and custom fields twice, then restored `enable_sensor=0`; the post-test
anti-idle and system-health gates passed. The custom usage field returned
`0x0205`, while the custom values are still raw and not semantically decoded.
Thus PID `0002` is not absent on Linux, but its custom interface is not yet a
standard IIO/orientation API. The four-way display-rotation result above is
separate from this Windows Simple Orientation HID report; do not claim HID
report parity until its raw fields are mapped and its values are validated.

The standard IIO matrices are source-regression tested, checked on the tablet,
and visually validated in all four physical display orientations above. A
45-second live capture on 2026-10-04 sampled the standard accelerometer and
LUID `0205` while the tablet was rotated through four orientations. The
standard accelerometer changed with movement; on the custom sensor,
`event-sensor-event` changed from `5` to `1`, but
`data-field-custom-value_1` stayed `0` and the other custom field did not yet
yield a defensible orientation mapping. The sensor was restored to
`enable_sensor=0`, and anti-idle, kernel-version and system-health gates passed.
This confirms custom-HID motion response, not its orientation mapping. Mapping
that report remains open.

The HID `event-sensor-event` transition `5 -> 1` is not an orientation value:
the HID Sensor Usage Tables define selector 5 as “Change Sensitivity” and 1 as
“State Changed”. The actual orientation value must come from the custom data
fields, which remain undecoded ([HID Sensor Usages, Table 4](https://www.usb.org/sites/default/files/hutrr39b_0.pdf#page=27)).

A follow-up 45-second IIO buffer capture on 2026-10-04 temporarily enabled the
accelerometer buffer and restored it to `0`. It yielded 104 frames, with no
confirmed four-pose markers; the sampled vector stayed near `(-0.692, 0.048,
-0.718) g`. Treat this as inconclusive rather than a regression or validation.
The capture path needs synchronized pose markers and continuous report checks.

After the matrix fix, the integrated 6.14 kernel completed a 10-second
RTC-timed s2idle cycle on 2026-10-04. PMC S0I3 residency increased by about
9.77 seconds; the system returned to `running` with the anti-idle inhibitor
active. A post-resume hardware smoke exited 0 and rechecked Wi-Fi, Bluetooth,
audio, display/touch, cameras, and all standard IIO devices; the accelerometer,
gyro, and magnetometer matrices and compass scale matched expected values.
After resume, the user confirmed the display remained correctly oriented while physically inverted.

A targeted LUID `0205` probe found `data-field-custom-usage=0x0205` and
`data-field-custom-value_27` with logical range `0..5`; Windows defines the
same six-value `SimpleOrientation` enum (`0` not rotated, `1..3` quarter-turns,
`4/5` face-up/down). Its current value was `3`. The kernel usage table maps
`custom-value_27` and `_28` to HID usages `0x055e` and `0x055f`; USB HUT marks
`0x054a..0x055f` as custom-reserved, so `_28`'s monotonic value is not a
documented timestamp and its semantics remain unknown. The range match alone
is only a candidate, not a field mapping
([Microsoft enum](https://learn.microsoft.com/en-us/uwp/api/windows.devices.sensors.simpleorientation?view=winrt-26100),
[USB HID Sensor Usages](https://www.usb.org/sites/default/files/hutrr39b_0.pdf)).
A further 45-second capture again kept value `27` at `3` and the accelerometer
near one static vector; no pose transition was observed, and physical movement
was not confirmed. Each probe restored `enable_sensor=0`.

On a subsequent 45-second capture, the tablet remained stationary (the user
confirmed it was neither moved nor laid flat). The event selector stayed at
`5`, candidate orientation field `value_27` stayed at `0`, and the
accelerometer raw vector stayed at `(-691984, 49166, -717726)` throughout.
This is an unlabelled stationary pose, not a level/face-up reference pose; the
vector cannot serve as a calibrated axis baseline. It does not validate the
orientation mapping or indicate a motion-report regression. The sensor was
restored to `enable_sensor=0`, and post-capture anti-idle/system-health checks
passed.

## 12. TFA9890 factory DSP path remains opt-in

Both TFA9890 amplifiers enumerate on the stable 6.14 path, but the default
`SND_SOC_TFA989X` driver bypasses CoolFlux DSP. The Xiaomi/NXP factory DSP
driver and container parser are now integrated as an optional alternative;
the Mi Pad 2 defconfig deliberately keeps the known-working driver selected.
Kconfig prevents both drivers from binding to the same `i2c:tfa9890` clients.

The target has `/lib/firmware/tfa98xx.cnt` with the expected factory profiles.
The candidate driver passes source checks and a local `W=1` object build, but
OEM DSP startup, left/right profile output, playback stop/resume, recovery,
power use, and suspend/resume still need real-device validation before making
it the default. Do not treat device enumeration or compile success as proof of
OEM audio parity.

The candidate's I2C remove path clears the monitor flag, synchronously cancels
the self-rearming delayed monitor and queued DSP-init work, then destroys its
workqueue. The 2026-10-04 live attempt loaded both factory containers (three
profiles each), but did not establish DSP/audio success. Persistent pstore
shows the test shell blocked in `unbind_store -> device_release_driver_internal
-> snd_soc_unregister_component_by_driver -> soc_cleanup_card_resources ->
snd_card_disconnect_sync`, followed by the configured hung-task panic. This is
ASoC waiting for open ALSA card file references during unbind, not evidence of
a DSP workqueue deadlock. On the recovered stable boot, a read-only audit found
PipeWire and WirePlumber holding `/dev/snd/controlC0` even with no sink inputs;
the old test checked PCM handles only. It also used unbounded raw `hw:0,0`
playback, while the kernel logged `no backend DAIs enabled for Audio Port`, so
that run did not verify the OEM HiFi route.

The temporary live-test runner now quiesces PipeWire/WirePlumber and checks all
`/dev/snd/*` references before unbind, starts the user audio stack to verify the
OEM HiFi sink and uses bounded `paplay` bursts, then quiesces it again before
cleanup. On 2026-10-04, the revised end-to-end test ran on the one-shot 6.14
image (`aab9eb8a...`): both candidate devices bound and loaded their three
factory profiles; the OEM HiFi sink appeared and two bounded playback bursts
completed. However, neither playback caused the expected `factory DSP init
ret=0` log (nor an explicit DSP-init error), so the test correctly exited
failure rather than claiming DSP startup. Its cleanup did complete: both amps
returned to `tfa989x`, PipeWire restored the HiFi sink, no PCM handles or test
processes remained, and the system/anti-idle gates passed. The test hardening
prevented a repeat of the earlier ASoC teardown hang, but routed playback and
factory DSP initialization remain unverified. Keep the stock TFA989X driver
selected until the trigger/DAI path is diagnosed and candidate DSP startup,
playback, teardown, restoration and audible output all pass on-device.

An acoustic-loopback attempt on 2026-10-04 captured the same two 440 Hz bursts
from both the PipeWire sink monitor and the built-in microphone. The sink
monitor showed a clear 440 Hz peak (~5,000 PCM counts), proving only that PCM
reached PipeWire's speaker sink. The built-in-mic capture was entirely zero
even while its Pulse source stream was open and `STO1 ADC Capture Switch` was
on; therefore this is not evidence of physical speaker output or silence. A
short PC-microphone fallback could not open the local DirectShow device. The
probe briefly raised the speaker sink volume from 41% to 70% for two 1 kHz
bursts, then restored it to 41%; system health and anti-idle checks passed.
Acoustic output remains unverified until a working mic/loopback route is
available. Keep the stock amp driver selected meanwhile.

A bounded 1 kHz DAPM probe during live `paplay` playback on the stock amp
driver narrowed the failure further. `Ext Spk Switch` was on, but the machine
`Ext Spk` widget, RT5659 `SPO Playback`/`SPK Amp`/`SPOL`/`SPOR`, and both TFA
`HiFi Playback` streams remained inactive; RT5659 `AIF1 Playback` was active.
The TFA codec-to-codec DAI-link widgets existed, but their playback streams
were inactive. This shows the accepted PCM never made it onto the active
speaker backend; it is not a volume-only problem.

The machine DAPM map previously connected `Ext Spk` only to the RT5659
`SPOL`/`SPOR` pins, while this tablet's speakers terminate at TFA9890
`OUT Left`/`OUT Right`. The working-tree fix connects the machine speaker
endpoint to those TFA output widgets instead. Its `W=1` machine-driver object
compile succeeded (one pre-existing unused-GPIO warning); module link and
live-device validation remain outstanding. ASoC's [codec-to-codec DAI-link
documentation](https://docs.kernel.org/sound/soc/codec-to-codec.html) confirms
these links need a valid DAPM endpoint to activate. Do not treat this source
change as audible-output verification until AIF2/TFA streams and DSP init are
seen active on device.

On 2026-10-04, a complete Clang 21 build succeeded and produced the machine
module with the running kernel's exact `6.14.0-mipad2-cachyos` vermagic and
`CONFIG_MODVERSIONS` CRCs. The module was swapped live (no reboot or `/boot`
change), retaining the stock TFA989X driver. During bounded 1 kHz playback,
`Ext Spk`, both codec-to-codec DAPM links, both TFA AIF inputs and both TFA
output widgets changed to `On`; the RT5659 AIF1 playback stream was active.
This validates DAPM power-path activation, not the analog signal or acoustic
output. The TFA `HiFi Playback` and RT5659 `AIF2 Capture` stream flags still
reported inactive, so end-to-end sample transfer remains unverified.

A post-fix 440 Hz loopback test again detected the tone in PipeWire's sink
monitor (peak about 5,000 PCM counts), but the tablet microphone capture was
all-zero PCM. Independent Windows mic capture also failed: DirectShow had no
usable capture pin and OpenAL/WASAPI returned `0x80070032`. Therefore no
acoustic output claim is justified yet. The live module remains loaded only
for this session; the stable boot entry and stock amplifier driver remain
unchanged. Anti-idle/system health passed and the speaker volume was restored.
