# Mi Pad 2 firmware and userspace helpers

`fix_file/` 保存 **Xiaomi Mi Pad 2 (latte)** 在当前内核之外仍需要的固件、用户态配置、systemd 服务和实机检查工具。

内核本身请使用：

```bash
make xiaomipad2_defconfig
```

完整的当前状态见仓库根目录 [`MIPAD2_STATUS.md`](../MIPAD2_STATUS.md)。

## 推荐先做的事

启动到新内核后先执行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

这比逐个猜驱动是否加载更适合判断问题发生在内核、固件、用户态还是 USB/BIOS 设置。

## Wi-Fi - BCM4356

当前 `xiaomipad2_defconfig` 已启用 `brcmfmac` PCIe 支持，驱动本身不需要额外 patch。

Mi Pad 2 仍需要正确的 Broadcom firmware/NVRAM。仓库提供设备 NVRAM：

```text
fix_file/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt
```

通常复制到：

```bash
sudo install -Dm644 \
  'fix_file/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt' \
  '/usr/lib/firmware/brcm/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt'
```

部分发行版的 `/lib/firmware` 是 `/usr/lib/firmware` 的兼容路径，两者不需要重复放置。

如果驱动日志实际请求的是通用名字，可再按日志复制/重命名为：

```text
brcmfmac4356-pcie.txt
```

不要只凭文件名猜测，优先查看：

```bash
dmesg | grep -iE 'brcm|brcmfmac|firmware'
```

## Bluetooth - BCM4356A2

默认配置已经启用 Broadcom HCI UART/BT 支持，仍需要 controller firmware：

```text
fix_file/BCM4356A2.hcd
```

安装示例：

```bash
sudo install -Dm644 fix_file/BCM4356A2.hcd \
  /usr/lib/firmware/brcm/BCM4356A2.hcd
```

验证：

```bash
dmesg | grep -iE 'bluetooth|btbcm|hci'
bluetoothctl list
```

## Audio - RT5659

音频不再建议依赖零散 `amixer` 命令。当前仓库提供 UCM 包：

```bash
makepkg -si -f fix_file/packages/mipad2-alsa-ucm
```

详细说明见 [`audio.md`](./audio.md)。

## Camera - Intel AtomISP / OV5693 / T4KA3

当前相机相关代码已经进入内核树：

- `CONFIG_VIDEO_ATOMISP=m`
- `CONFIG_VIDEO_OV5693=m`
- `CONFIG_VIDEO_T4KA3=m`
- `CONFIG_VIDEO_DW9719=m`
- T4KA3 驱动：`drivers/media/i2c/t4ka3.c`
- 后摄 DW9761 VCM 由当前 `dw9719` 路径兼容支持

`latte-camera-t4ka3.patch` 仅保留为回移/上游参考，**当前仓库不需要再次手工应用它**。

推荐使用相机辅助包安装 AtomISP firmware 和模块加载配置：

```bash
makepkg -si -f fix_file/packages/mipad2-camera-support
```

该包会安装：

```text
/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin
/etc/modules-load.d/mipad2-camera.conf
```

手动检查：

```bash
sudo modprobe atomisp
sudo modprobe ov5693
sudo modprobe t4ka3
sudo modprobe dw9719

dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97'
media-ctl -p
v4l2-ctl --list-devices
```

> **当前相机仍是实验性功能。** CI 会编译 AtomISP/T4KA3/DW9719 等关键对象，但这不代表两颗摄像头已经稳定完成实机 streaming。近期代码仍在修正 T4KA3 frame interval、AtomISP HMM 分配和 runtime 状态。

需要主动采集测试时再执行：

```bash
sudo MIPAD2_ACTIVE_CAMERA_TEST=1 sh fix_file/tests/mipad2-hardware-smoke.sh
```

## Bottom capacitive Menu / Home / Back keys

旧文档曾要求手工创建 `/etc/udev/hwdb.d/60-keyboard.hwdb` 修复底部三个电容键。

**当前内核已经不需要这个 workaround。** `drivers/hid/hid-multitouch.c` 已针对 Mi Pad 2 的 `2808:509c` 控制器直接处理：

- `S` chord -> `KEY_MENU`
- `Esc` -> `KEY_HOME`
- `Backspace/Delete` -> `KEY_BACK`
- chord 使用的 LeftCtrl / LeftMeta modifier 会被过滤

如果你是从旧内核升级，建议删除之前专门为 Mi Pad 2 添加的自定义 hwdb 规则，然后更新 hwdb/重启，避免双重映射：

```bash
sudo systemd-hwdb update
```

## USB OTG / Gadget / serial console

当前默认配置已经覆盖 DWC3 dual-role、USB configfs serial/ACM 和 USB serial console 所需内核选项。

但 Mi Pad 2 要真正出现 UDC/Device 模式，仍可能需要 BIOS/UEFI 把 USB OTG 切到 PCI Mode。详细步骤见：

[`USB_OTG_Gadget.md`](./USB_OTG_Gadget.md)

仓库目前保留两个用户态方案：

- `mipad2-usb-serial`：当前 USB ACM `ttyGS0` 串口控制台方案，适合调试/恢复。
- `mipad2-usb-gadget`：USB Ethernet configfs gadget。

`mipad2-usb-serial` 与旧 gadget 包声明冲突/替代关系，不要同时安装。

## Recovery and test helpers

### Local recovery

```bash
makepkg -si -f fix_file/packages/mipad2-recovery
```

恢复脚本会对 `/boot` 做安全检查。执行任何恢复操作前仍应人工确认 ESP/boot filesystem 挂载正确。

### No-idle test mode

```bash
makepkg -si -f fix_file/packages/mipad2-test-no-idle
```

这个包只用于定位 idle / suspend 相关硬件问题，不建议作为日常长期配置。

## Video decode acceleration

当前 Mi Pad 2 实机已经验证以下用户态组合可用：

- `libva 2.24.0`
- `Intel i965 driver 2.4.5`

确认不需要强制降级到 `libva 2.21.0-1`。

验证：

```bash
vainfo
```

应能看到类似：

```text
Intel i965 driver for Intel(R) CherryView
```

以及 MPEG-2 / H.264 / VC-1 等硬件解码入口。若发行版后续默认切换到不兼容的 VA-API driver，优先安装/选择 `libva-intel-driver` / `i965`，不要为了这个问题修改内核。

## Package index

| 目录 | 用途 |
| --- | --- |
| `packages/mipad2-alsa-ucm` | RT5659 UCM |
| `packages/mipad2-camera-support` | AtomISP firmware + camera module loading |
| `packages/mipad2-recovery` | 本地 boot 备份/恢复 |
| `packages/mipad2-test-no-idle` | 硬件排障用 no-idle 模式 |
| `packages/mipad2-usb-gadget` | USB Ethernet gadget |
| `packages/mipad2-usb-serial` | USB ACM serial console |
