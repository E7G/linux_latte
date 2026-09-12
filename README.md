# Linux kernel for Xiaomi Mi Pad 2 (latte)

这是面向 **Xiaomi Mi Pad 2 / latte** 的 Linux 内核树，当前基于 Linux **6.14**，目标是在尽量保留主线内核结构的同时，补齐 Mi Pad 2 所需的驱动、默认配置、固件和少量用户态辅助文件。

> 文档同步基线：`main` @ `bc851227`（2026-09-11）。  
> 这里的“已集成”表示代码/默认配置已经进入仓库，不等同于所有发行版、所有固件环境下都已经完成实机验证。

原始 Linux 内核构建说明仍保留在 [`README`](./README) 和 [`Documentation/`](./Documentation/) 中。

## 当前重点

| 功能 | 当前状态 | 说明 |
| --- | --- | --- |
| Mi Pad 2 专用配置 | ✅ 已集成 | `arch/x86/configs/xiaomipad2_defconfig`，内核后缀为 `-mipad2-complete` |
| Intel i915 显示 / DRM | ✅ 内核配置已覆盖 | 硬件 smoke test 会检查 DRM card、render node 和背光 |
| 触摸屏 | ✅ 已集成 | FTSC1000 触摸/输入路径保留；底部 Menu / Home / Back 已直接在 `hid-multitouch` 中修正 |
| BCM4356 Wi-Fi | 🟡 驱动已集成 | `brcmfmac` 以模块启用，仍需要匹配的 NVRAM/firmware |
| BCM4356A2 Bluetooth | 🟡 驱动已集成 | HCI UART + Broadcom 支持已启用，仍需要 `BCM4356A2.hcd` |
| RT5659 音频 | 🟡 内核 + UCM | 推荐配合 `fix_file/packages/mipad2-alsa-ucm` 使用 |
| USB DWC3 dual-role | 🟡 已集成 | Host/Device 角色已配置；Device/Gadget 模式还取决于 BIOS/UEFI 的 OTG 设置 |
| USB ACM 串口调试 | 🟡 可用辅助包 | 使用 `mipad2-usb-serial`，用于 `ttyGS0` 调试/恢复 |
| AtomISP 相机 | 🧪 实验性 | AtomISP、OV5693、T4KA3、DW9719 均已进入默认配置，但仍在持续修复实机 streaming 路径 |
| VA-API 视频解码 | ✅ 用户态已验证 | 当前文档记录的实机组合为 libva 2.24.0 + Intel i965 driver 2.4.5 |

更细的代码/运行时状态见 [`MIPAD2_STATUS.md`](./MIPAD2_STATUS.md)。

## 构建

```bash
make xiaomipad2_defconfig
make -j"$(nproc)"
```

主要产物：

```text
arch/x86/boot/bzImage
```

如果需要安装模块，请使用与你当前发行版启动方式相匹配的流程。不要在不清楚 ESP、`/boot` 和当前引导项布局的情况下直接覆盖已有可启动内核。

## Mi Pad 2 辅助文件

设备相关的固件、UCM、systemd 服务和测试工具集中放在 [`fix_file/`](./fix_file/)：

- `fix_file/README.md`：固件与辅助包总入口。
- `fix_file/audio.md`：RT5659 / PipeWire / UCM 配置。
- `fix_file/USB_OTG_Gadget.md`：USB OTG、Gadget、串口设备模式说明。
- `fix_file/packages/mipad2-camera-support`：AtomISP 固件和相机模块自动加载配置。
- `fix_file/packages/mipad2-recovery`：本机备份/恢复工具。
- `fix_file/packages/mipad2-test-no-idle`：仅用于排障的 no-idle 测试模式。
- `fix_file/packages/mipad2-usb-serial`：USB ACM 串口控制台。
- `fix_file/tests/mipad2-hardware-smoke.sh`：只读为主的硬件 smoke test。

Arch/Arch-based 系统可在对应包目录中使用：

```bash
makepkg -si
```

## 硬件 smoke test

启动到新内核后，可以先运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

脚本会检查 Wi-Fi、Bluetooth、ALSA、背光、触摸输入、DRM、LED、电池/充电、IIO、USB UDC、媒体节点以及 T4KA3/VCM 等关键路径。

相机主动采集测试默认**不会**执行。只有明确准备测试相机 streaming 时才使用：

```bash
sudo MIPAD2_ACTIVE_CAMERA_TEST=1 sh fix_file/tests/mipad2-hardware-smoke.sh
```

## 相机说明

当前相机栈已经不是单纯的外置 patch：

- `CONFIG_VIDEO_ATOMISP=m`
- `CONFIG_VIDEO_OV5693=m`
- `CONFIG_VIDEO_T4KA3=m`
- `CONFIG_VIDEO_DW9719=m`
- T4KA3 驱动位于 `drivers/media/i2c/t4ka3.c`
- Mi Pad 2 的 T4KA3 AtomISP bridge 配置已经进入内核树
- AtomISP firmware 可由 `mipad2-camera-support` 安装到 `/usr/lib/firmware/intel/ipu/`

`.github/workflows/mipad2-camera-check.yml` 会做配置和关键对象的编译检查，但 **CI 编译成功不代表两颗摄像头已经稳定完成实机采集**。近期代码仍在处理 T4KA3 frame interval、AtomISP HMM 分配和传感器运行时状态，因此相机继续标记为实验性。

## 注意事项

修改 BIOS/UEFI setup variable、分区、ESP 或启动内核都存在让设备无法正常启动的风险。涉及 USB OTG setup variable 前先阅读 [`fix_file/USB_OTG_Gadget.md`](./fix_file/USB_OTG_Gadget.md)，并保留可用的恢复介质/原内核。

如果提交硬件问题，建议同时附上：

```bash
uname -a
dmesg
lspci -nnk
lsusb
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```
