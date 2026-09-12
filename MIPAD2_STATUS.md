# Mi Pad 2 hardware / code status

本文档描述仓库当前代码能够明确确认的状态，避免把“驱动存在”“默认配置启用”“CI 能编译”和“已经完成实机验证”混为一谈。

同步基线：`main` @ `bc851227`（2026-09-11）。

## 状态含义

- ✅ **Integrated**：Mi Pad 2 所需代码/配置已经进入仓库，当前没有在文档中标记为实验路径。
- 🟡 **Needs setup**：代码已进入仓库，但仍依赖固件、用户态配置、BIOS/UEFI 设置或额外包。
- 🧪 **Experimental**：代码和编译检查已经存在，但实机功能仍在持续调试，不能视为完整支持。
- ⚪ **Not claimed**：仓库没有足够信息证明该功能已经稳定，不在文档中作完成承诺。

## 核心功能

| 子系统 | 代码/配置状态 | 当前说明 |
| --- | --- | --- |
| Kernel target | ✅ | `make xiaomipad2_defconfig`，`CONFIG_LOCALVERSION="-mipad2-complete"` |
| EFI | ✅ | `CONFIG_EFI=y`、`CONFIG_EFI_STUB=y`、`CONFIG_EFI_MIXED=y` |
| Intel i915 / DRM | ✅ | 默认配置包含 Intel 图形栈；硬件 smoke test 检查 `/sys/class/drm/card0` 与 `renderD128` |
| LCD backlight | ✅ | smoke test 会检查 `/sys/class/backlight/*` |
| Touchscreen | ✅ | 输入/触摸配置已启用；实机检测脚本识别 FTSC1000 等设备名 |
| Bottom capacitive keys | ✅ | Mi Pad 2 `2808:509c` HID 键盘已在 `hid-multitouch.c` 中直接映射 Menu / Home / Back，不再要求额外 hwdb 才能获得正确键值 |
| Wi-Fi (BCM4356) | 🟡 | `CONFIG_BRCMFMAC=m`、PCIe 支持启用；需要正确的 Broadcom firmware/NVRAM，仓库提供 Mi Pad 2 NVRAM |
| Bluetooth (BCM4356A2) | 🟡 | `CONFIG_BT_HCIUART=m`、`CONFIG_BT_HCIUART_BCM=y`、`CONFIG_BT_BCM=m`；需要 Broadcom HCD firmware |
| Audio (RT5659) | 🟡 | 内核音频路径已维护；推荐安装 `mipad2-alsa-ucm` 让 PipeWire/WirePlumber 正确管理 Speaker/Headset/Mic |
| Battery / fuel gauge | ✅/🟡 | 默认配置包含 `CONFIG_BATTERY_BQ27XXX=y`；smoke test 会检查 Battery power_supply，具体电量/休眠后的行为仍应以实机为准 |
| Charger (BQ25890) | ✅/🟡 | `CONFIG_CHARGER_BQ25890=y`；smoke test 会检查 USB/Mains charger power_supply |
| USB DWC3 dual-role | 🟡 | 默认配置要求 DWC3 dual-role + PCI；Gadget/UDC 是否出现还取决于 BIOS/UEFI 的 USB OTG 模式 |
| USB ACM serial | 🟡 | 内核已启用 USB serial/configfs ACM 所需配置，`mipad2-usb-serial` 提供持久化 `ttyGS0` 控制台 |
| USB Ethernet gadget | 🟡 | 旧的 `mipad2-usb-gadget` 仍保留；`mipad2-usb-serial` 与它冲突并声明替代关系，二者不要同时安装 |
| VA-API decode | ✅ | `fix_file/README.md` 记录实机可用组合：libva 2.24.0 + Intel i965 driver 2.4.5；这是用户态驱动选择，不需要为了它修改内核 |
| IIO sensors | ⚪ | smoke test 已覆盖 ALS、accelerometer、gyro、magnetometer 等节点，但仅凭仓库代码不能承诺所有传感器在所有用户态环境下稳定可用 |
| Suspend / resume | ⚪ | 当前文档不把深度休眠/唤醒完整性标为“已完成”；遇到恢复后音频/USB/相机问题应分别收集日志 |

## Camera

相机是当前最需要区分“代码已集成”和“实机稳定”的部分。

| 组件 | 状态 | 说明 |
| --- | --- | --- |
| Intel AtomISP | 🧪 | `CONFIG_VIDEO_ATOMISP=m`；仓库包含针对 Mi Pad 2 的 bridge/defaults/HMM 修正 |
| OV5693 | 🧪 | `CONFIG_VIDEO_OV5693=m`，使用内核树中的 OV5693 驱动 |
| T4KA3 | 🧪 | `CONFIG_VIDEO_T4KA3=m`，驱动已直接进入 `drivers/media/i2c/t4ka3.c`，不再要求手工应用 `latte-camera-t4ka3.patch` |
| Rear VCM | 🧪 | Mi Pad 2 的 DW9761 由当前 `dw9719` 路径兼容支持，`CONFIG_VIDEO_DW9719=m` |
| AtomISP firmware | 🟡 | `mipad2-camera-support` 安装 `shisp_2401a0_v21.bin` 到 `/usr/lib/firmware/intel/ipu/` |
| CI compile check | ✅ | `.github/workflows/mipad2-camera-check.yml` 会验证配置、关键 bridge/default 值以及相关对象编译 |
| Stable capture | 🧪 | **不宣称已经稳定完成。** 最近提交仍在修复 T4KA3 frame interval、AtomISP HMM page allocation 和 sensor runtime 状态 |

用于查看拓扑：

```bash
sudo modprobe atomisp
sudo modprobe ov5693
sudo modprobe t4ka3
sudo modprobe dw9719

dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97'
media-ctl -p
v4l2-ctl --list-devices
```

主动 streaming 测试只有在你明确准备调相机时再运行：

```bash
sudo MIPAD2_ACTIVE_CAMERA_TEST=1 sh fix_file/tests/mipad2-hardware-smoke.sh
```

## Repository helper packages

| 包 | 用途 | 备注 |
| --- | --- | --- |
| `mipad2-alsa-ucm` | RT5659 UCM | 正常桌面音频推荐安装 |
| `mipad2-camera-support` | AtomISP firmware + modules-load | 相机实验必需的辅助包之一 |
| `mipad2-recovery` | 本地 boot 备份/恢复 | 先确认 `/boot` 确实挂载到预期文件系统 |
| `mipad2-test-no-idle` | 禁用部分 idle 以排查硬件问题 | **只用于测试，不建议长期日用** |
| `mipad2-usb-gadget` | USB Ethernet configfs gadget | 旧/独立用途 |
| `mipad2-usb-serial` | USB ACM serial console | 当前串口调试方案；与 `mipad2-usb-gadget` 冲突/替代 |

## 验证原则

`.github/workflows/mipad2-camera-check.yml` 主要证明“默认配置和关键对象仍能编译，并且预期代码没有在重构中丢失”。它不能替代实机验证。

建议实机每次更新内核后至少执行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

如果某一项 FAIL/MISS，请附上完整 smoke 输出和对应子系统的 `dmesg`，再决定是驱动问题、固件问题、用户态配置问题还是 BIOS/UEFI 模式问题。
