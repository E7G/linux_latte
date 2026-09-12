# Mi Pad 2 运行时文件与用户空间集成

`fix_file/` 现在主要保存 **固件、用户空间配置、辅助包、测试脚本和历史参考文件**。当前内核已经直接集成了不少过去需要额外打补丁的 Mi Pad 2 支持，因此不要把这里的所有文件都当成“必须手工应用的修复”。

当前建议先使用仓库的 `xiaomipad2_defconfig` 编译/安装内核，再按实际缺少的固件或用户空间功能补充本目录内容。

## 目录概览

- [`audio.md`](./audio.md)：RT5659 / TFA9890 音频与 ALSA UCM 使用说明；
- [`USB_OTG_Gadget.md`](./USB_OTG_Gadget.md)：USB device mode、UDC 与 USB 串口调试；
- `packages/mipad2-alsa-ucm`：音频 UCM 配置；
- `packages/mipad2-camera-support`：AtomISP 固件、模块加载顺序与 systemd 集成；
- `packages/mipad2-usb-serial`：当前推荐的 CDC ACM USB 串口调试方案；
- `packages/mipad2-recovery`：恢复辅助工具；
- `packages/mipad2-test-no-idle`：真机测试时可选的防休眠模式；
- [`tests/`](./tests/)：硬件 smoke test、前后摄选择和采集测试；
- `latte-camera-t4ka3.patch`：仅用于历史/回移参考，**当前内核不要重复应用**。

## Wi-Fi：BCM4356

当前 `xiaomipad2_defconfig` 将 `cfg80211` / `brcmfmac` 作为模块构建。设备仍需要合适的 BCM4356 NVRAM。

将：

```text
fix_file/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt
```

复制到：

```text
/lib/firmware/brcm/
```

优先保留带 DMI/设备名的文件名。如果驱动仍然找不到固件，先查看：

```bash
dmesg | grep -Ei 'brcmfmac|firmware'
```

只有在日志明确请求通用文件名时，再考虑额外复制为 `brcmfmac4356-pcie.txt`；不要在没有查看日志的情况下直接覆盖或重命名唯一副本。

## 蓝牙：BCM4356

将：

```text
fix_file/BCM4356A2.hcd
```

复制到：

```text
/lib/firmware/brcm/
```

当前内核使用模块化的 Broadcom HCI UART 支持。验证时先看：

```bash
ls /sys/class/bluetooth/
dmesg | grep -Ei 'Bluetooth|hci|bcm'
```

## Intel AtomISP / 摄像头

当前相机支持已经不是“外部 patch + 手工复制驱动”的模式：

- OV5693 前摄使用内核树中的驱动；
- T4KA3 后摄驱动已经集成到当前内核树；
- 后摄 DW9761 VCM 由 `dw9719` 兼容支持；
- AtomISP/Mi Pad 2 bridge 与默认格式处理已经在内核树中；
- `latte-camera-t4ka3.patch` 只保留作参考，不应再次应用；
- `shisp_2401a0_v21.bin` 仍是运行时需要的 AtomISP 固件。

### 推荐：使用 camera support 包

在 Arch/使用 `makepkg` 的系统上：

```bash
cd fix_file/packages/mipad2-camera-support
makepkg -si
```

这个包负责安装 AtomISP 固件，并提供相机模块加载顺序和 systemd 集成。

### 手工固件方式

如果不使用上述包，可至少复制：

```bash
sudo install -Dm644 fix_file/shisp_2401a0_v21.bin \
    /lib/firmware/shisp_2401a0_v21.bin
```

然后检查实际加载情况：

```bash
sudo modprobe atomisp
sudo modprobe ov5693
sudo modprobe t4ka3
sudo modprobe dw9719

dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97|firmware'
media-ctl -p
v4l2-ctl --list-devices
```

> 相机仍属于实验/持续修复区域。驱动和媒体拓扑能枚举出来，不等于所有 V4L2 应用都已经稳定可用。请使用 [`tests/README.md`](./tests/README.md) 中的测试方法验证。

## 音频

当前仓库提供 `mipad2-alsa-ucm`，用于 RT5659 与双 TFA9890 的用户空间路由。详见：

- [`audio.md`](./audio.md)
- `packages/mipad2-alsa-ucm/`

不要再沿用早期仅靠固定 `amixer` 命令修右声道的做法；当前 Speaker/Headset/Mic 路由应交给 UCM 管理。

## USB device mode / USB 串口

当前内核已经启用 DWC3 PCI dual-role 与 ConfigFS ACM 支持。推荐的调试方案是：

```bash
cd fix_file/packages/mipad2-usb-serial
makepkg -si
sudo systemctl enable --now mipad2-usb-serial.service
```

成功后平板侧应出现：

```text
/dev/ttyGS0
```

Windows 主机一般会看到 **Mi Pad 2 USB Serial** 对应的 COM 口，可按 `115200 8N1` 使用。

`mipad2-usb-serial` 会替代旧的 `mipad2-usb-gadget`，两者不能同时绑定同一个 UDC。旧的 USB Ethernet gadget 方案因此只作为兼容/历史方案保留。

如果 `/sys/class/udc/` 下没有实际 UDC，请先阅读 [`USB_OTG_Gadget.md`](./USB_OTG_Gadget.md) 检查固件/BIOS 的 OTG 模式。

## 触摸屏底部电容按键

当前内核树已经包含 Mi Pad 2 对 `FTSC1000:00` 底部按键的专用 HID 处理。**正常情况下不再要求手工添加下面的 hwdb 规则。**

如果使用旧内核、旧打包版本，或者当前 userspace 下按键仍然映射错误，可将以下规则作为 fallback：

```text
###########################################################
# Xiaomi
###########################################################

evdev:name:FTSC1000:00 2808:509C Keyboard:dmi:*:svnXiaomiInc:pnMipad2:*
 KEYBOARD_KEY_700e0=reserved
 KEYBOARD_KEY_700e3=reserved
 KEYBOARD_KEY_70016=menu
 KEYBOARD_KEY_70029=leftmeta
 KEYBOARD_KEY_7002a=back
```

添加到 `/etc/udev/hwdb.d/60-keyboard.hwdb` 后，需要按发行版方式更新 hwdb 并重新触发设备/重启。不要在内核按键已经正确时重复叠加用户空间映射。

## 视频硬解

Mi Pad 2 实机已验证 `libva 2.24.0` + `Intel i965 driver 2.4.5` 可用，不需要为了本仓库强制降级到 `libva 2.21.0-1`。

```bash
vainfo
```

正常应看到 `Intel i965 driver for Intel(R) CherryView`，以及 MPEG-2 / H.264 / VC-1 等硬件解码入口。

这部分主要是用户空间 VA-API 驱动选择，不是本内核需要额外打补丁的功能。若发行版默认驱动不兼容，优先检查 `libva-intel-driver` / i965 选择。

## 推荐的真机检查

冷启动、相机使用后、耳机插拔后以及 suspend/resume 后建议执行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

需要专门检查相机时再执行：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

硬件 smoke test 默认不会主动开始摄像头采集；相机测试属于主动硬件测试，AtomISP 异常时可能需要重启恢复。
