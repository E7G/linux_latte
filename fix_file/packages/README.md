# Mi Pad 2 用户空间辅助包

本目录保存与当前 `linux_latte` 内核配套的 **Arch Linux / `makepkg` 风格本地包**。它们不是内核本身的一部分，也不是所有发行版都必须安装的依赖。

如果使用 Arch 或其他直接使用 `makepkg` 的环境，通用安装方式是进入对应包目录后执行：

```bash
cd fix_file/packages/<package-name>
makepkg -si
```

不要把包目录作为 `makepkg` 的最后一个参数；`makepkg` 应在包含 `PKGBUILD` 的目录中运行。

## 当前包状态

| 包 | 状态 | 用途 / 注意事项 |
| --- | --- | --- |
| `mipad2-alsa-ucm` | **推荐** | 安装 RT5659 + 双 TFA9890 的 ALSA UCM2 profile，供 PipeWire/WirePlumber 或其他 UCM2 音频栈使用。 |
| `mipad2-camera-support` | **推荐（使用摄像头时）** | 安装 AtomISP 2401 固件到 `/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin`，并安装 Mi Pad 2 相机模块加载配置。 |
| `mipad2-usb-serial` | **推荐（调试/恢复）** | 配置 ConfigFS CDC ACM gadget，提供 `/dev/ttyGS0`、serial getty，并利用当前内核的 gadget serial console 支持获取 printk。 |
| `mipad2-recovery` | 可选 | 提供 `mp2-backup` / `mp2-recover`。面向本项目常用的独立 `/boot` FAT + BTRFS root + Timeshift 布局。 |
| `mipad2-test-no-idle` | 可选，仅测试 | 临时抑制 GNOME idle blanking / suspend，便于长时间真机测试；不建议作为日常默认电源策略。 |
| `mipad2-usb-gadget` | **旧方案 / 不推荐新装** | 旧的 USB Ethernet ConfigFS gadget。当前 `mipad2-usb-serial` 在 PKGBUILD 中明确 `conflicts` / `replaces` 它，两者不能同时绑定同一个 UDC。 |

## 关键说明

### 相机固件

当前 AtomISP 代码首先请求：

```text
intel/ipu/shisp_2401a0_v21.bin
```

因此推荐使用 `mipad2-camera-support` 的安装路径：

```text
/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin
```

驱动仍保留对旧顶层文件名 `shisp_2401a0_v21.bin` 的兼容回退，但新安装不应以旧路径作为首选。

### USB gadget 冲突

`mipad2-usb-serial` 的 PKGBUILD 已声明：

```text
conflicts=(mipad2-usb-gadget)
replaces=(mipad2-usb-gadget)
```

这是有意设计：当前推荐无 Wi-Fi 调试路径是 CDC ACM 串口，而不是旧 USB Ethernet gadget。若服务提示 UDC busy，先确认旧 gadget 没有仍在运行。

### Recovery 包不是通用恢复系统

`mipad2-recovery` 假定特定的文件系统与 Timeshift 使用方式。安装或运行前请先阅读包内 README，并确认自己的 `/boot` 与 root 布局一致。

## 与内核版本的关系

这些辅助包按当前 `xiaomipad2_defconfig` 和当前仓库中的 Mi Pad 2 驱动行为编写。升级到其他内核、切换到发行版原生内核，或改变驱动 built-in/module 方式后，应重新核对：

- 模块名与加载顺序；
- firmware request 路径；
- UDC / ConfigFS 能力；
- ALSA card / UCM 名称；
- systemd service 的启动条件。

真机升级后建议运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

相机相关变更再额外执行：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```
