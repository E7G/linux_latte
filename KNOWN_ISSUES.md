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
output. A second route dump showed `IF2 ADC Mux` selecting `DAC_REF`, followed
by active `IF2 ADC`, `AIF2TX`, `AIF2 Capture`, both C2C link widgets, TFA AIF
inputs, and TFA outputs. The TFA `HiFi Playback` and RT5659 `AIF2 Capture`
stream labels still read inactive; these labels do not indicate an active FE
PCM on the static C2C route. Thus the DAPM graph reaches the TFA outputs, but
acoustic output remains unverified.

A post-fix 440 Hz loopback test again detected the tone in PipeWire's sink
monitor (peak about 5,000 PCM counts), but the tablet microphone capture was
all-zero PCM. Independent Windows mic capture also failed: DirectShow had no
usable capture pin and OpenAL/WASAPI returned `0x80070032`. Therefore no
acoustic output claim is justified yet. The live module remains loaded only
for this session; the stable boot entry and stock amplifier driver remain
unchanged. Anti-idle/system health passed and the speaker volume was restored.

The user subsequently reported no audible output with a freshly built live
machine module. A read-only snapshot during an active PipeWire sink input
showed `Ext Spk`, both C2C DAI-link widgets, both TFA AIF inputs, amp power,
and both output widgets `On`; the RT5659 had `DIG_INF23_DATA=0x2000`,
`I2S2_SDP=0x0000`, `PWR_DIG_1=0xc080`, and `GLB_CLK=0x4000`. Both TFA9890
`STATUSREG`s read `0x0a5d`; **do not treat `NOCLK` alone as proof of missing
external I2S clocks**. That value also has the `CLKS` flag set while `PLLS` and
`AREFS` are clear according to the local field definitions, so it shows an
unhealthy/not-ready state but does not isolate the clock fault. PCM/DAPM
activation is verified; audible output remains unfixed. Android's init value
is `DIG_INF23_DATA=0x2801`; the active Linux value `0x2000` confirms
`IF2 ADC IN = DAC_REF`. The separate `IF2 DAC` selector is the RT5659 receive
path, not the source sent to the TFA amps, so Linux now leaves it DAPM-managed.

Follow-up source audit on 2026-10-04 compared the Android machine driver and
the Linux 6.14 ASoC C2C implementation. Android routes each TFA `Playback`
endpoint from RT5659 `AIF2 Capture`, and configures the RT5659 AIF2 as clock
provider while each TFA is a consumer. The Linux C2C links have the same
capture-to-playback direction; `snd_soc_get_stream_cpu()` maps C2C playback to
CPU capture, and `snd_soc_runtime_set_dai_fmt()` flips the provider flags for
the CPU DAI. The active-stream **cached** register snapshot also showed RT5659 AIF2 master
mode (`I2S2_SDP=0`), AIF2 enabled (`PWR_DIG_1` bit 14), PLL source selected
(`GLB_CLK=0x4000`), PLL powered (`PWR_ANLG_3` bit 6), 32fs BCLK, and I2S2 pins
selected rather than GPIO (`GPIO_CTRL_3=0`). The 2026-10-05 hardware-bypassed
audit below subsequently invalidated the clock conclusions from those cached
values. The C2C source/configuration checks make a simple C2C
direction or master/slave inversion unlikely, but register values do not prove
the waveform reaches both TFA input pins. Next evidence needed: capture the
TFA I2S/system-control registers and `PLLS`/`AREFS`/`CLKS` during playback,
and verify the RT5659 BCLK/WS electrically or with a trustworthy hardware
clock monitor. A later SSH snapshot was taken idle with no sink input, so its
C2C widgets being `Off` is expected and is not playback evidence.

Latest read-only SSH snapshot (2026-10-04): PipeWire's selected speaker sink
was `SUSPENDED` with no sink-input; DAPM C2C links were `Off`, so this snapshot
cannot diagnose an active playback failure. Software speaker volume was 47%,
ALSA `Speaker` was 44% and `Mono` was on; neither speaker path was muted.
Both TFA9890s were bound to the generic `tfa989x` driver. Earlier in this boot,
the Xiaomi factory `tfa98xx` driver loaded its left/right containers and was
then removed before `tfa989x` rebound both devices. A prior active-stream test
did show the PCM/DAPM route powered through both TFA outputs, yet the user heard
no sound. Therefore the remaining leading suspect is TFA amplifier/DSP or the
physical I2S-to-amp signal, not a muted desktop sink; capture must be repeated
while actual playback is active before narrowing further.

Review of the earlier tone harness found its 440 Hz PCM peak was only 2,200 / 32,767
(6.7% full scale). Combined with the observed PipeWire sink level (-19.67 dB)
and ALSA Speaker level (-21 dB), the stimulus was roughly -64 dBFS before TFA
amplifier gain. The user's earlier “no sound” result from that short tone was
therefore not a valid acoustic-failure verdict. A corrected two-second test
used a stronger 440 Hz stimulus and temporarily raised PipeWire/Speaker/Mono to
80%, restoring the original levels afterward. The PCM stream and DAPM route
were active, but the user still heard no sound. The anti-idle/system-health
gates passed and the previous volume levels were restored. This rules out the
earlier near-silent stimulus as an explanation; physical output is confirmed
absent for this test, while the electrical cause is still unresolved.

On 2026-10-05 a follow-up **digital-zero-only** stream was used to inspect the
full live DAPM path without producing another audible test. Both TFA9890s had
their playback input, selected AIF input, input mux, power supply, amp-enable,
and `OUT Left`/`OUT Right` widgets `On`; RT5659 `AIF2 Capture`, `AIF2TX`,
`DAC_REF` and `AIF1 Playback` were also `On`. The `HiFi Playback` DAPM stream
labels displayed `inactive` even though the PCM substream was `RUNNING` and the
widgets/routes were powered, so those labels alone are not proof that the PCM
missed the backend.

During that silent stream, a read-only I2C snapshot showed TFA I2S registers
`0x880b` (left) and `0x884b` (right), and SYS_CTRL `0x8208` on both chips:
PWDN was clear and AMPE was set, while DCA and CFE were clear. After playback
stopped, SYS_CTRL read `0x8201` on both (PWDN set, AMPE clear), confirming DAPM
power sequencing. Both TFA `STATUSREG`s again read `0x0a5d`. These reads still
cannot prove BCLK/WS/data waveform at the amp pins or acoustic output.

The earlier proposal to enable DCA in the generic bypass path was withdrawn
after checking the [NXP TFA9890A datasheet, sections 8.1.2 and 8.4](https://yibeiic-shop.oss-cn-hangzhou.aliyuncs.com/media/collection/tfa9890aukn1z-8WzIAdME-VobW9VJNj.pdf).
Follower mode supplies the amplifier from the battery without boost. NXP
explicitly recommends keeping boost disabled with the DSP bypassed. Thus the
generic driver's DCA=0/CFE=0 is intentional, not evidence of the silence's
root cause; the DSP driver's DCA=1 is a different operating mode. No DCA write
was performed. Continue with clock/input selection and factory DSP startup,
not an unprotected boost test. The datasheet also states that valid BCK and WS
are required for operating mode, even when PWDN is clear.

### 2026-10-05: RT5659 reset/rebind cache-coherence failure identified

A temporary exact-vermagic module used `regmap_read_bypassed()` under regmap's
normal locking to compare cached values with actual hardware during a
digital-zero stream. It did not use forced I2C access or change amplifier
settings. The critical RT5659 differences were:

| Register | Cached configuration | Actual hardware before recovery |
| --- | --- | --- |
| `I2S1_SDP` (0x70) | 0x8103 | 0x8000 |
| `I2S2_SDP` (0x71) | 0x0000 (clock provider) | 0x8000 (clock consumer) |
| `PLL_CTRL_1` (0x81) | 0x0f03 | 0x0000 |
| `PLL_CTRL_2` (0x82) | 0x3000 | 0x0001 |
| `GPIO_CTRL_1` (0xc0) | 0xc800 | 0x0000 |

Power registers matched cache, and the platform MCLK was enabled at 19.2 MHz,
but neither fact proved that the interface/PLL configuration reached hardware.
RT5659's component `remove()` resets the chip while its I2C regmap and cached
DAI/PLL state survive a sound-card/machine-driver rebind. The old callback did
not mark the regcache dirty, and component `probe()` did not sync it. Subsequent
cached update-bits/unchanged-PLL fast paths could therefore leave reset hardware
in consumer mode with reset PLL parameters. This is a concrete failure in the
live module-reload workflow, not evidence that the C2C provider flags were wrong.

An explicit cache-dirty/sync recovery returned 0. A subsequent digital-zero
stream showed actual `I2S1_SDP=0x8103`, `I2S2_SDP=0x0000`, and
`PLL_CTRL_1=0x0f03`, matching cache. Both TFA status registers changed from
0x0a5d to 0xd85f: PLLS/AREFS/AMPS were set and NOCLK was clear. The user then
confirmed hearing two 2-second 440 Hz tones at the unchanged desktop/mixer
volume. Thus generic bypass speaker output is acoustically confirmed for this
recovered 6.14 session; this does not validate the optional factory DSP driver.

The source fix marks RT5659 regcache dirty after component reset, syncs it before
component probe registers DAPM controls, and propagates probe/control/resume sync
errors. `mipad2-rt5659-rebind-test.py` compiles and executes the actual four
callbacks with mocked persistent cache/hardware, including injected reset,
sync, and control-registration failures. The Clang `W=1` RT5659/RL6231 module
build completed with strict modpost and exact running-kernel vermagic.

The candidate codec was loaded temporarily, then the known-working machine
module was removed and reinserted without unloading the codec. After this
formerly failing sequence, **without any diagnostic cache repair**, actual
interface/PLL registers matched the expected configuration and both TFA chips
passed PLLS/AREFS/AMPS/NOCLK checks. The PCM was RUNNING, desktop audio restarted,
and system/anti-idle health gates passed (`REBIND_PASS=1`, `CLEANUP_RC=0`).
Post-candidate acoustic confirmation and persistence across reboot must be
recorded separately rather than inferred from this silent test.

The tested codec module was subsequently installed into the existing
`6.14.0-mipad2-cachyos` module directory. The original compressed module and the
fixed candidate were saved under
`/var/lib/mipad2-kernel-backups/rt5659-rebind-20261005T0227/`; compressed readback
SHA-256 and installed/running source versions matched. Neither 6.14 stable nor
recovery initramfs contained RT5659, so no boot image/GRUB update was needed or
performed. Installation passed; a reboot has **not** yet verified persistence.

A subsequent 10-second RTC `s2idle` suspend/resume increased the kernel's
successful-suspend counter from 0 to 1. Three digital-zero start/stop cycles
after resume passed PCM RUNNING, actual AIF/PLL configuration, and both TFA
clock/amp-ready checks. At the end, PCM was closed, TFA SYS_CTRL was 0x8201,
RT5659 digital/PLL power was off, and GLB_CLK had returned to RCCLK (0x8000).
SSH/system health and the anti-idle inhibitor remained available
(`RTC_RESUME_AUDIO_CLOCK_PASS=1`). This is an electrical-status/power regression,
not a substitute for post-resume listening.

The prior Android `DUMMY_2=0x001d` hypothesis was also tested temporarily with
digital zeros. Hardware/cache readback verified the write and restoration to
0x0000; neither TFA clock status improved. No permanent DUMMY_2 quirk was added.
The matching factory container (SHA-256
`83709da84f22b5c0ff1f7568478b3ecbfc1c1c29bc3814a8be8a64426f3c2c2a`)
selects 48 kHz and left/right raw input in its bypass profiles, consistent with
the generic driver's active I2S settings. DCA/boost was not changed.

`mipad2-tfa-format-test.py` separately executes the real generic TFA set-format
callback with 38 fault-injection/format/field-preservation cases. It now
propagates regmap read/write errors and rejects unimplemented clock inversion;
the OEM I2S reset-format bits are preserved. Its `W=1` object build passed. This
is error-handling hardening, not the cause of the restored audible output, and
the running built-in TFA driver has not been replaced with that source change.

The same source audit found a concrete defect in the optional Xiaomi DSP
driver: its DAPM graph created only an unconnected `I2S1` input and an
`NXP Output Mixer`, while this board's speaker routes require `OUT Left` and
`OUT Right`. The DSP candidate therefore lacked board-facing output endpoints.
The driver now creates the matching endpoint for Mi Pad 2 addresses `0x34`
(left) and `0x37` (right), connects each per-device playback stream through the
mixer to that endpoint, and propagates DAPM registration errors. The modified
driver object compiles with Clang 21 and `W=1`. A full `vmlinux` build then
generated matching `vmlinux.o`/`Module.symvers`; strict modpost linked the
candidate `.ko` without unresolved-symbol errors. Its vermagic is
`6.14.0-mipad2-cachyos SMP preempt mod_unload modversions`, matching the
running kernel release/config fields. The earlier warning-only `.ko` was
discarded.

On 2026-10-04 the strict candidate was temporarily loaded on the running 6.14
system for a **silent DAPM-registration probe**. Both amplifiers bound to
`tfa98xx`, both factory containers exposed three profiles, and the component
DAPM trees contained `OUT Left` / `OUT Right` routed through each `NXP Output
Mixer`. No audio stream or tone was started, so both endpoints correctly read
`Off`; this proves runtime registration only, not DSP initialization or sound.
Cleanup restored both devices to `tfa989x`, restored the original PipeWire
speaker route (`AUDIO_RESTORED=yes`), and passed the anti-idle/system health
gates. Keep the stock amp driver selected until bounded playback, DSP init,
audible output, teardown, and suspend/resume all pass on-device.

### 2026-10-05: factory DSP warm-handoff recovery and scoped live validation

After the RT5659 cache fix, a six-second digital-zero stream initialized both
factory DSPs successfully for the first time in this test sequence. However,
repeating the generic-to-factory driver handoff exposed a second defect:
the old code returned `ret=0` while SYS_CTRL was 0x8218 (CFE clear) and the
amplifier input remained raw rather than DSP. The ACS latch was already clear
from the previous factory initialization, but the intervening generic driver
had disabled/bypassed CF. A new factory-driver instance incorrectly trusted
that warm latch and skipped loading its own container/register configuration.
Thus a successful log message alone was insufficient evidence of DSP playback.

The factory driver now marks each component probe as requiring full DSP
initialization. `tfa98xx_dsp_start()` forces the existing Xiaomi/NXP cold-start
sequence until its own initialization/unmute succeeds; a partial profile or
volume/start failure invalidates this ownership flag again. Normal warm restarts
after a successful initialization remain warm. The real start callback is
compiled and exercised by `mipad2-tfa-start-test.py` with mocked operations for
fresh warm-latch handoff, normal idle restart, recovery, parameter errors, and
failed/partial-write rollback. The Clang `W=1` candidate module build and strict
modpost completed with exact running-kernel vermagic.

The freshly built candidate SHA-256 is
`43b77eed855313838b255678682a3b60cb62069b6ef597fd99356f9964b3ba0c`.
Two separate on-device **silent** handoff/initialization/teardown runs passed:
both amps reported current-run DSP init `ret=0`; while PCM remained RUNNING,
both real (REGCACHE_NONE) register sets had STATUS 0xd05f and SYS_CTRL 0x827c,
PLLS/AREFS/AMPS set, NOCLK clear, CFE/AMPE/DCA enabled, PWDN clear, and CHSA=2
(DSP input). Factory MTP remained 0x0003; hardware-bypassed pre/post reads of
the trim words stayed 0x7f7d (left) and 0x7f55 (right). No calibration/trim
change was observed. Both runs restored `tfa989x`, the HiFi desktop sink,
original volumes, and the active anti-idle inhibitor; the subsequent broad
hardware enumeration/configuration smoke test passed.

The live harness now defaults to `MIPAD2_TFA_TEST_MODE=silent`, checks that its
six-second WAV contains only digital zeros before touching drivers, and does
not raise volume in silent mode. Audible mode must be explicitly selected and
requires a listening result; neither mode's init/clock gate proves acoustic
output. Each test writes a unique kernel-log marker and requires both physical
amps' container/init evidence after that marker. Eight executable log-parser
tests reject old successes, a single-amp success, missing/duplicate markers,
unrelated messages, deferred-only probes, and a latest initialization failure.
The settled hardware check caught the warm-handoff false success above.

Default amp selection remains generic. Factory-DSP listening, profile/volume
controls, sustained playback, and suspend/resume remain open; do not promote
the optional candidate based only on these silent successes.

### 2026-10-05: pending DSP-init work drained on mute

The factory mute callback previously drained only its delayed monitor work,
not the separate DSP-init work queued by that monitor/trigger. The init worker
also did not recheck `desired_running`. A valid queued-after-mute schedule could
therefore initialize/power the amp after playback was stopped. The new
`mipad2-tfa-mute-worker-test.py` compiles and executes both actual callbacks with
a controllable mock worker schedule: before the fix it failed the assertion
that a stale post-mute init must leave the amp off. This reproduces the logic
defect, not a measured kernel-scheduler race on the tablet.

Mute now drains both work items outside the worker's shared mutex; the init
worker checks the current playback request under that mutex and ignores stale
requests. This complements synchronous cancellation's limitation in the
presence of racing enqueues described by the
[upstream workqueue API](https://kernel.org/doc/html/v6.12/core-api/workqueue.html#c.cancel_work_sync).
The real-callback regression passes after the fix, including error paths,
safe-probe mode, and assertions that neither cancellation holds the mutex.
The full offline audio test set, Clang `W=1`, and strict modpost also passed.

The updated exact-vermagic candidate SHA-256 is
`bc788ce6a43b7a7ca14ae2e8f288dd39ae8e631a96ec50b60ea2fc646843db03`.
One live temporary-driver run exercised two six-second digital-zero streams,
with seven seconds of normal desktop idle after each (audio services were not
stopped to force the idle check). Both active phases had real STATUS 0xd05f,
SYS_CTRL 0x827c, DSP input, and MTP 0x0003 on both amps. Both idle phases had
PCM closed, STATUS 0x025d (AREFS/AMPS clear), and SYS_CTRL 0x8265 (PWDN set).
The second stream successfully resumed the same driver instance. Current-run
DSP-init logs, generic-driver restoration, HiFi sink restoration, original
volume restoration, and anti-idle checks all passed. This is a bounded
start/stop/idle regression, not a long-duration scheduler stress proof.

The C2C path still schedules its initial monitor after one second; short-sound
startup latency is not yet optimized or acoustically verified. Keep this and
the outstanding factory-DSP acoustic/resume gates open rather than claiming
full audio completion.

### 2026-10-05: C2C startup latency and Stop control share a lifecycle

The next actual-callback regression found that the ALSA Stop control still
cancelled only monitor work, changed worker-owned state without its mutex, and
could leave monitoring disabled when later C2C playback unmuted. Before the
fix the extended executable harness failed the explicit-Stop assertion that
both workers must be drained. This is a callback-logic reproduction, not a
measured concurrent kernel race.

Stop and C2C mute now share `tfa98xx_set_running()`: disable monitor rearming,
drain both workers outside their mutex, then serialize state and DSP stop.
Stopped DSP state becomes PENDING. Unmute restores the monitor flag and uses
`mod_delayed_work(..., 0)` rather than delaying a short stream by HZ. Factory
startup retains its power-on/AREF/PLL ordering; no pre-start PLL/AREF gate was
added while the amplifier is in PWDN. The upstream
[C2C DAPM implementation](https://github.com/torvalds/linux/blob/v6.14/sound/soc/soc-dapm.c)
uses digital mute for this route, not the normal PCM trigger path; the
[workqueue API](https://kernel.org/doc/html/v6.12/core-api/workqueue.html#c.mod_delayed_work)
documents advancing pending work with zero delay.

The exact-vermagic W=1/strict-modpost candidate SHA-256 is
`b2c919735b4814aa7914d277bdb284ba99e2723559ef4a6aeec0f752838fdbe7`.
One live temporary session passed two six-second digital-zero streams, normal
desktop idle after each, and both Stop controls during the first RUNNING PCM.
Stopping produced STATUS/SYS_CTRL 0x025d/0x8265 and monitor=0 on both amps;
restarting produced 0xd05f/0x827c, DSP input and monitor=1. MTP stayed 0x0003.
All current-run init returns were zero. Generic drivers, original levels,
HiFi sink, and anti-idle inhibitor were restored.

Current-run dmesg timestamps show the first C2C unmute-to-full-init completion
about 299 ms (previous run about 1354 ms). First firmware loading occurred
during WirePlumber route probing; the final warm restart after desktop idle
completed about 17 ms after C2C unmute (previous run about 1150 ms). These are
callback-to-init timings from bounded silent runs, not microphone latency,
first-audible-sample timing, or proof that every short notification is intact.
Cold DSP firmware load still has real cost. Acoustic, profile/volume,
sustained, concurrency, suspend/resume and reboot gates remain open.

### 2026-10-05: complete isolated 6.14 r2 kernel staged, not boot-tested

A complete LLVM/ThinLTO `bzImage modules` build from source commit
`b1f68fb71c0936ee5d8f2e59faf7aae903dddfbc` finished with exit zero, including
the built-in generic TFA989x format fix, RT5659 cache-rebind fix, and machine
audio changes. Its release is `6.14.0-mipad2-integrated-r2`; comparing the
final config against the tablet's actual `/proc/config.gz` found only the
LOCALVERSION change. The image header and embedded config matched; all 34
installed compressed modules have the new exact vermagic. This build was
not a zero-warning W=1 claim. The optional factory DSP remains unselected.

The 20 MiB kernel/modules bundle SHA-256 is
`3e73d7375b9ef4186085028b94a42302b705a904b48b5ad0d9adaacaeba3c977`.
It includes a source/config and file-hash manifest but no device-specific
initramfs. The unpublished integration commit has not been pushed to GitHub.
The user's unrelated modified litmus test was preserved and not compiled.

The tablet has an isolated `/usr/lib/modules/6.14.0-mipad2-integrated-r2`
tree and `/var/lib/mipad2-kernel/6.14.0-mipad2-integrated-r2` kernel/initramfs.
An explicit image-path mkinitcpio build with post hooks disabled succeeded;
lsinitcpio reports the new release. User-space GRUB-fstest read both images
through the Btrfs subvolume paths and compared them byte-for-byte. A preview
GRUB entry passed syntax checking but was not installed or selected. This
is not proof that the installed UEFI GRUB can boot the new images.

All existing `/boot` file hashes were unchanged; no stable/recovery/6.18
image was deleted to free space. `/boot` still has only about 15 MiB free,
so the candidate uses the root filesystem instead. The saved default remains
`mipad2-bqdiag1`, next_entry is empty, and the current kernel is still
6.14.0-mipad2-cachyos. No reboot occurred in this staging test. New-release
boot, hardware/audio/orientation regression, suspend/resume and persistence
remain required before selecting it as a normal default.

### 2026-10-05: isolated r2 one-shot attempted; SSH boot not observed

A candidate-only serial initramfs was generated with the normal hooks plus
an early ACM service ordered before `sysroot.mount`, timeout 15 seconds.
Its content, script syntax, GRUB-fstest byte comparison, and live already-bound
no-rebind path passed. The initial custom `-D` mkinitcpio attempt correctly
failed because `-D` replaces default hook directories; the corrected build
explicitly retained the default hook paths and completed successfully.
The malformed intermediate image was overwritten before any selection.
These checks do not prove the cold initramfs service executed on hardware.

The r2 menu entry was appended to `custom.cfg` after preserving its complete
original content under the root-filesystem candidate backup. All other /boot
file hashes stayed unchanged. The saved default remained `mipad2-bqdiag1`;
only next_entry was selected for r2. The candidate was given the same lockup,
panic and logging diagnostics as the known-running 6.14 command line, then
one reboot was issued.

A bounded 420-second SSH monitor, keyed to the previous actual boot_id
`af9b1729-40df-4247-a8ac-ce863f41e34c`, ended without observing any new SSH
boot. The USB capture also ended without enumerating the target serial
VID/PID. A later user cable acknowledgement was followed by another host
port check, still showing only Bluetooth serial ports. No r2 boot/console
log is available to locate the failing phase. Do not infer successful boot
from build/staging checks, or attribute this to Btrfs/GRUB/kernel/initramfs
without new evidence. No repeated candidate reboot was issued or default
promotion performed. Recovery to the preserved stable item and collection
of GRUB environment, prior-boot journal and pstore are the next gates.

### 2026-10-05: r2 direct-root boot and silent resume regression passed

The tablet subsequently recovered to `6.14.0-mipad2-cachyos-navkeys-bqdiag1`,
boot_id `d5c9820c-2115-45e5-bf00-2fd27aa2dc2b`. The saved default was still
`mipad2-bqdiag1`, next_entry was consumed, anti-idle was active, and USB ACM
enumerated as COM17. The newly archived pstore records were old-kernel
`Shutdown#1` data, not an r2 panic. No intervening r2 journal was present.

A separate, bounded isolation boot used the exact r2 image on Btrfs with
the known direct-root `/dev/mmcblk0p2` path and existing early microcode,
but no systemd initramfs, early USB hook or ttyGS0 kernel console. The host
observed the new release over SSH after 212.2 seconds; USB serial also
reported the actual release. The new boot_id was
`394f9cee-617a-432a-8e2d-4bb91ca02397`. This proves the installed UEFI GRUB
can load this r2 kernel from Btrfs and the kernel can reach the desktop
userspace. It does not identify whether the previous missing boot was
caused by normal initramfs, the additional hook, the console, or timing.
Systemd reported firmware 12.578 s, loader 4.691 s, kernel 83.747 s and
userspace 12.441 s. Verbose EFI framebuffer logging remains enabled;
these diagnostic timings are not production boot performance results.

The full read-only hardware smoke passed. All 26 loaded modules had the
exact r2 vermagic and matching on-disk/runtime srcversions; the running
embedded config matched the staged config byte-for-byte. Both amplifiers
were bound to generic TFA989x, the optional factory DSP was not loaded,
PipeWire had the HiFi speaker sink, and no systemd unit was failed. These
are enumeration/provenance checks, not proof of all physical functions.

A digital-zero PipeWire stream succeeded before and after one RTC
10-second s2idle cycle. Kernel PM logs confirm suspend entry/exit and the
same boot_id survived; post-resume hardware smoke and anti-idle checks
passed. Process monotonic elapsed time excludes suspended wall time;
use the PM log rather than the short subprocess elapsed field as evidence
of the suspend interval. No acoustic test occurred in this regression.
New-release sound and physical rotation verification remain open.

The command line's `hardlockup_panic=1` was reported as unknown and did
not enable the hard-lockup panic sysctl. Source inspection of watchdog.c
confirmed the supported boot setting is `nmi_watchdog=panic,1`. Future
r2 entries were corrected; no claim is made that the running direct-root
boot had hard-lockup panic enabled. A separate normal-initramfs entry,
without the early USB hook or ttyGS0 console, was syntax/hash checked and
prepared, not selected or rebooted. Stable/recovery/6.18 image contents
and the saved default remain unchanged. The current r2 is still a test,
not the validated default or a declaration of complete hardware support.

### 2026-10-05: ordinary initramfs boot and clean helper packaging verified

The normal-initramfs isolation entry booted the same r2 kernel successfully,
without the early USB hook or ttyGS0 kernel console. Its actual boot_id is
`1b1589b9-3b61-4438-b780-e81bc2501445`; SSH and USB ACM both reported r2.
Systemd recorded a 6.026-second initrd and reached graphical.target after
11.992 seconds of root userspace. The corrected hard-lockup boot option
set the live hardlockup_panic sysctl to 1. Saved bqdiag1 and an empty
next_entry were confirmed. Normal initramfs is therefore no longer an
unproven boot path; the original early-hook/console combination still is.

Post-boot smoke, all 26 loaded-module provenance checks, and the running
config comparison passed again. Rear and front 1280x720 YU12 short capture
each returned 4,153,344 bytes. Rear raw OTP checks, the Android-compatible
544-byte calibration layout (CRC16/IBM 7e85), and front 320-byte calibrated
OTP (CRC16/IBM 7bdf) passed on the actual r2 modules. Post-camera smoke
passed without a reboot. Frame acquisition and calibration packing are
verified; color/3A quality, physical rotation and new-release acoustic
acceptance are not inferred from these results.

Real Arch makepkg clean builds exposed another integration defect: helper
recipes depended on tracked files under src/ and did not declare sources.
In disposable user-owned directories, makepkg -C removed those files and
the ALSA/camera recipes both failed with exit 4. All six helper packages
now keep their 18 unchanged payload files beside PKGBUILD, explicitly
declare source and SHA-256 arrays, and have incremented pkgrel. The source
path changes were carried through CI and the no-idle regression script.

The new offline source-staging regression passed for all six recipes.
On the tablet, source integrity, native clean build, source-only archive,
and a fresh clean rebuild from that archive passed for each package (24
checks). Binary payload paths/hashes matched across source round trips;
the source files remained unchanged. No test helper package was installed
and no service was enabled/disabled by this packaging test. Build-only
dependencies fakeroot/debugedit and their dependencies were installed
with pacman -S --needed, without a database refresh or kernel upgrade.
The optional legacy Ethernet package remains discouraged; building it
does not mean it was activated alongside the recommended serial gadget.


### 2026-10-05: r3 boot passed; cold speaker-route defect reproduced

The full LLVM21/ThinLTO r3 build (production source ce83e0f34) booted via
the validated serial initramfs. Boot ID was 12e20872-604d-45c5-b12b-cf4aa5b0ce97.
Systemd reported firmware 12.638 s, loader 3.831 s, kernel 5.575 s, initrd
5.413 s and userspace 10.942 s. Verbose initcall logging was removed, so this
is not a controlled performance comparison with previous diagnostic boots.
All 26 loaded modules and the embedded config matched the original bundle;
hardware smoke, front/rear capture, both Android OTP layouts and six camera
switch cycles passed. A 10-second RTC s2idle cycle recovered the same boot,
SSH, ACM and silent playback. CLOCK_BOOTTIME/wall elapsed was 11.184 s;
process monotonic elapsed was 2.137 s and excludes suspended time. No new
UBSAN/BUG/WARNING was observed in these checks. W=1 build warnings remain.

The initial GRUB-fstest comparison used stale CLEAN raw-device page-cache
data (zero bytes/missing paths), despite filesystem sync. After advising
POSIX_FADV_DONTNEED on the read-only block-device FD, all three images
matched Linux reads byte-for-byte. No filesystem rewrite, global cache
drop, block-device write or BLKFLSBUF was used. This host-side test artifact
is not evidence that the UEFI bootloader reads stale data.

The user then reported no sound from two successful PipeWire tone streams
after resume. A signed, temporary read-only probe found RT5659 hardware/cache
coherence intact: AIF2=0000 and PLL_CTRL_1=0f03. Nevertheless IF2 ADC Mux's
active DAPM route was IF_ADC2 while the hardware/control reported DAC_REF=2;
both amps remained PWDN (SYS_CTRL=8201, STATUS=0a5d) during a running PCM.
Refreshing the mux through ALSA (0 then 2) connected DAC_REF and produced
STATUS=d85f/SYS_CTRL=8208 in both amps. This is a separate graph-state bug,
not recurrence of the earlier regcache reset/rebind defect. The probe was
unloaded; expected out-of-tree taint changed 1088 to 5184.

The board now removes the raw mux write from link init. Late probe creates
the DAPM controls after routes are registered, then selects DAC_REF through
the normal DAPM enum callback. Hardware, kcontrol cache and graph stay
consistent. This follows the routing/control model described in the
[kernel DAPM documentation](https://docs.kernel.org/sound/soc/dapm.html).
No always-on amp, forced hardware register patch, global sanitizer change
or userspace startup-toggle workaround was added.

The real callback's offline ordering/fault model and a signed r3 machine
module W=1 build passed (one pre-existing unused GPIO-table warning).
On hardware, seeding reset-default IF_ADC2 before a card rebind reproduced
the stock mismatch; two equivalent seeded candidate rebinds selected the
DAC_REF graph correctly without a post-bind toggle. Restoring ALSA/PipeWire
preserved the graph and both amps became ready during a digital-zero stream.
This reset-default-seeded rebind is not a substitute for an actual cold
boot of the final module, post-resume acoustic output or prolonged playback.
The original r3 archive lacks this later fix and must not be advertised as
the final validated audio build. A temporary candidate machine is live;
the separate installation record, if present, is authoritative for disk
persistence. Saved GRUB default remains bqdiag1; 6.18/recovery images remain
unchanged. Listening confirmation after the new route and final cold-boot
persistence remain separate gates.

## 2026-10-05 integrated 6.14 r4 cold-boot and camera ABI audit

The in-tree 6.14.0-mipad2-integrated-r4 build (source e37f7faa6) booted
one-shot with GRUB's saved bqdiag1 default unchanged. All 26 loaded modules
match the running tree, and no out-of-tree module taint remains. Both cameras
captured three frames each, the RT5659/TFA route survived cold boot and 10s
s2idle without a manual DAPM toggle, and the user heard two short tones.
Guided user-held portrait-up, landscape-left, landscape-right and
portrait-down orientations all had matching proxy state and normal display.

`v4l2-compliance 1.32.0 -d /dev/video0` on this r4 boot found 8 failing
groups. A narrower, read-only C ioctl regression independently reproduced
two concrete ABI violations: `VIDIOC_ENUMINPUT` exposed the ISP port in the
reserved field for input 1, and `VIDIOC_ENUM_FRAMESIZES` accepted an unknown
pixel format. The V4L2 contract requires reserved input fields to be zero,
and enumeration must reject unsupported formats. The local follow-up changes
only these two paths; other six compliance failures, including AtomISP's
private capturemode and multi-open/buffer behavior, remain open. Do not claim
full V4L2 compliance until the entire suite passes on the new kernel.

The [AtomISP staging TODO](drivers/staging/media/atomisp/TODO) explicitly
notes that image quality needs a 3A userspace library. Windows CPF/AIQB color
matrices cannot safely be translated into guessed sensor register writes.
An upstream [libcamera AtomISP pipeline proposal](https://lists.libcamera.org/pipermail/libcamera-devel/2025-May/050239.html)
is a reference for userspace integration, not evidence that tuning is done.
