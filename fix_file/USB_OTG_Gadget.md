# Mi Pad 2 USB device / Gadget mode

Mi Pad 2 的 USB 控制器可以在 Linux 下作为 USB Device Controller (UDC) 使用。当前 `xiaomipad2_defconfig` 已启用项目实际使用的 DWC3 dual-role、configfs gadget、ECM/RNDIS、CDC ACM 和 USB serial console 相关配置。

这意味着内核侧能力已经具备，但 **BIOS/UEFI 必须先把 USB OTG 暴露为 PCI Mode**。如果 `/sys/class/udc` 下没有控制器，userspace gadget 脚本无法解决这个问题。

## 1. BIOS/UEFI 前置条件

### 已解锁完整菜单的 BIOS

将：

```text
USB OTG Support = PCI Mode
```

### 原厂 BIOS

已知 Setup 变量偏移为 `0x2a2`：

| 值 | 模式 |
| --- | --- |
| `0x0` | Disable |
| `0x1` | PCI Mode |
| `0x2` | ACPI Mode |
| `0x3` | AUTO（行为接近 ACPI Mode） |

原厂通常需要从 `0x3` 改为 `0x1`。

常见工具示例：

| 工具 | 示例 |
| --- | --- |
| `setup_var.efi` | EFI Shell: `setup_var.efi Setup:0x2a2=0x1` |
| GRUB `setup_var` 模块 | GRUB shell: `setup_var 0x2a2 0x1` |
| `ru.efi` | 可用于直接查看/修改 Setup 变量，但本仓库不提供已验证的按键操作流程 |

> 修改固件变量有风险。先记录原值，并确保你有可恢复的 EFI/固件环境。不要仅因为 gadget 服务启动失败就重复写 BIOS 变量。

修改后进入 Linux，先确认 UDC：

```bash
ls -l /sys/class/udc
```

目录中应至少出现一个实际控制器。若为空，先检查 BIOS 模式、DWC3 枚举和 `dmesg`，不要继续创建 configfs gadget。

## 2. 当前内核配置

项目 CI 会检查下列 Mi Pad 2 默认配置仍然存在：

```text
CONFIG_USB_DWC3_DUAL_ROLE=y
CONFIG_USB_DWC3_PCI=y
CONFIG_USB_CONFIGFS_SERIAL=y
CONFIG_USB_CONFIGFS_ACM=y
CONFIG_U_SERIAL_CONSOLE=y
```

默认配置同时包含 configfs ECM/RNDIS 等 USB 网络 gadget 功能，供 `mipad2-usb-gadget` 使用。

## 3. USB Ethernet（ECM/RNDIS）

本仓库提供 `mipad2-usb-gadget` 包。脚本创建一个 configfs gadget，同时挂接 ECM 和 RNDIS，并给平板端首个可用 USB 网络接口配置 `192.168.7.1/24`。

安装：

```bash
cd fix_file/packages/mipad2-usb-gadget
makepkg -si
sudo systemctl enable --now mipad2-usb-gadget.service
```

检查：

```bash
systemctl status mipad2-usb-gadget.service
ip addr show usb0
ip addr show usb1
```

不同主机系统可能选择 ECM 或 RNDIS，所以实际出现的接口可能是 `usb0` 或 `usb1`。

## 4. USB Serial 调试控制台

`mipad2-usb-serial` 使用 configfs CDC ACM 暴露 `/dev/ttyGS0`，并配套 `serial-getty@ttyGS0.service`。当前内核的 `CONFIG_U_SERIAL_CONSOLE=y` 还允许 gadget serial 注册为内核 console，并在 USB 枚举后回放 printk ring buffer，适合作为 Wi-Fi 不可用时的调试/恢复路径。

安装：

```bash
cd fix_file/packages/mipad2-usb-serial
makepkg -si
sudo systemctl enable --now mipad2-usb-serial.service
```

Windows 端通常会显示为 **Mi Pad 2 USB Serial** / COM 口，可按 `115200 8N1` 使用串口终端。

Linux 端检查：

```bash
systemctl status mipad2-usb-serial.service
ls -l /dev/ttyGS0
dmesg | tail -n 100
```

## 5. 两种 gadget 不能同时占用同一个 UDC

Mi Pad 2 只有一个可绑定的 UDC。`mipad2-usb-gadget`（网络）和 `mipad2-usb-serial`（ACM 串口）是当前仓库提供的两种 **替代配置**，不要同时 enable/start。

从网络模式切换到串口模式：

```bash
sudo systemctl disable --now mipad2-usb-gadget.service
sudo systemctl enable --now mipad2-usb-serial.service
```

从串口切回网络模式：

```bash
sudo systemctl disable --now mipad2-usb-serial.service
sudo systemctl enable --now mipad2-usb-gadget.service
```

旧内核如果自动绑定 legacy `g_ether`，`mipad2-usb-serial` 脚本会尝试先解绑它，让 configfs ACM function 能占用 UDC。

## 6. 排错

按下面顺序检查，比反复重装包更容易定位：

```bash
ls -l /sys/class/udc
lsmod | grep -E 'dwc3|libcomposite|u_serial'
mount | grep configfs
systemctl --failed
dmesg | grep -Ei 'dwc3|udc|gadget|configfs|ttyGS|usb'
```

如果 `/sys/class/udc` 有控制器但服务仍失败，再检查是否有另一个 gadget 已经占用 UDC：

```bash
find /sys/kernel/config/usb_gadget -maxdepth 2 -type f -name UDC -print -exec cat {} \;
```

硬件综合检查也会报告当前是否存在 UDC，以及 USB serial 是否已经 attach：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```
