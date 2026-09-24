# Known issues / 当前已知限制

本文档只记录与当前 `main` 分支和 `xiaomipad2_defconfig` 相符的已知限制。这里的“已集成”表示代码、配置或辅助工具已经存在，**不等于该功能已经在所有发行版和所有使用场景下完全稳定**。

## 1. AtomISP 摄像头仍是实验性功能

当前树已经包含 OV5693 前摄、T4KA3 后摄、DW9761 兼容对焦、Mi Pad 2 AtomISP bridge、1280×720 保守默认格式、frame-interval 处理以及近期的 AtomISP 内存分配健壮性修复。

但 AtomISP 仍是当前移植中风险最高的部分：

- 某些 V4L2 应用的格式协商流程可能与 AtomISP 不兼容；
- 前后摄切换、重复打开或异常退出后可能出现 pipeline 卡住；
- 用户空间 `timeout` 只能终止进程，不能保证已经卡死的内核驱动恢复；
- 遇到持续不可恢复的摄像头卡死时，当前可靠恢复方式仍可能是重启。

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

目前不能把 suspend/resume 视为所有外设都已完全稳定。每次修改 ACPI、电源管理、音频、无线、IIO 或媒体代码后，至少重新检查：

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

## 7. Recovery tools and layout checks

The current `mipad2-recovery` package derives the BTRFS root device from `/`, verifies `/boot` is mounted as VFAT, and binds each manual Timeshift snapshot to a separately checksummed boot archive. It refuses partial recovery when the matching archive is missing/corrupt or if the mounted `/boot` source changes during restore. It assumes root is BTRFS on a resolvable block device and that `/boot` is a separate VFAT filesystem; it does not mount partitions or recover arbitrary layouts.

After updating the package, run the mocked safety test:

```bash
sudo sh fix_file/tests/test-mipad2-recovery.sh
```

The test stubs Timeshift and filesystem commands; it verifies argument routing and guard behavior but does not replace an actual recovery drill from the USB serial console. Old global boot archives from earlier package versions are not automatically paired with snapshots.

## 8. 当前 defconfig 不是 hardened / generic distro 配置

`xiaomipad2_defconfig` 是面向设备可用性和开发测试的配置。目前包括：

- `CONFIG_LTO_CLANG_THIN=y`；
- `CONFIG_CPU_MITIGATIONS` 未启用；
- `CONFIG_VIRTUALIZATION` 未启用；
- 多个 Mi Pad 2 运行时组件采用模块形式。

如果设备用于处理不可信工作负载，尤其需要重新评估 CPU mitigations 等安全选项。若改变工具链或 defconfig，记得检查最终 `.config`，不要仅根据 defconfig 文件推断最终编译配置。

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
