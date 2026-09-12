# Mi Pad 2 USB OTG / Gadget / serial console

Mi Pad 2 的 USB Device/Gadget 功能可用于：

- USB ACM 串口控制台（`ttyGS0`）
- USB Ethernet gadget
- 其他基于 configfs 的 USB gadget 功能

当前 `xiaomipad2_defconfig` 已包含 DWC3 dual-role、PCI、USB configfs serial/ACM 和 USB serial console 所需配置。**如果 `/sys/class/udc` 没有实际 UDC，优先检查 BIOS/UEFI 的 USB OTG 模式，而不是继续改内核。**

## 1. BIOS / UEFI USB OTG mode

### 已解锁全部设置的 BIOS

将：

```text
USB OTG Support
```

设置为：

```text
PCI Mode
```

### 原厂 BIOS

当前已知 setup variable：

```text
Setup:0x2a2
```

将值从：

```text
0x3  AUTO
```

改成：

```text
0x1  PCI Mode
```

> 修改 UEFI setup variable 有导致设备无法正常启动或 USB 行为异常的风险。操作前保留可用的恢复方式，并确认变量/固件版本与自己的机器一致。

常见工具：

| 工具 | 示例 |
| --- | --- |
| `setup_var.efi` | EFI Shell：`setup_var.efi Setup:0x2a2=0x1` |
| GRUB `setup_var` | GRUB Shell：`setup_var 0x2a2 0x1` |
| `ru.efi` | 仓库旧说明未完成可靠实机验证，不建议按固定按键序列盲改 |

### USB OTG Support values

| 值 | 含义 |
| --- | --- |
| `0x0` | Disable |
| `0x1` | PCI Mode |
| `0x2` | ACPI Mode |
| `0x3` | AUTO（在当前设备上行为接近 ACPI Mode） |

修改并重新启动后先检查：

```bash
ls -l /sys/class/udc
```

至少应该出现一个实际 UDC。若目录为空，USB gadget 服务无法绑定。

## 2. 推荐调试方案：USB ACM serial

仓库当前提供：

```text
fix_file/packages/mipad2-usb-serial
```

它会创建一个 CDC ACM gadget，并使用：

```text
/dev/ttyGS0
```

作为 Linux 端串口。systemd 服务同时拉起：

```text
serial-getty@ttyGS0.service
```

安装（Arch/Arch-based）：

```bash
makepkg -si -f fix_file/packages/mipad2-usb-serial
sudo systemctl enable --now mipad2-usb-serial.service
```

检查：

```bash
systemctl status mipad2-usb-serial.service
ls -l /dev/ttyGS0
ls -l /sys/class/udc
```

连接 Windows 后设备应显示为 **Mi Pad 2 USB Serial**，通常会获得一个 COM 端口。串口参数：

```text
115200 8N1
```

当前默认配置启用了 `CONFIG_U_SERIAL_CONSOLE=y`，因此 USB 枚举完成后还可以把 `ttyGS0` 用作内核调试路径，并回放 printk ring buffer。这适合 Wi-Fi 不可用时排障。

## 3. USB Ethernet gadget

旧的 Ethernet 方案仍保留在：

```text
fix_file/packages/mipad2-usb-gadget
```

安装示例：

```bash
makepkg -si -f fix_file/packages/mipad2-usb-gadget
sudo systemctl enable --now mipad2-usb-gadget.service
```

但是当前 `mipad2-usb-serial` 包已经声明：

```text
conflicts=(mipad2-usb-gadget)
replaces=(mipad2-usb-gadget)
```

原因是单个 UDC 不能同时绑定旧的 Ethernet gadget 和当前 ACM gadget 配置。**串口调试与旧 Ethernet 包二选一，不要同时安装。**

## 4. 常见排查

### `/sys/class/udc` 为空

先检查 BIOS/UEFI 是否为 PCI Mode，再看：

```bash
dmesg | grep -Ei 'dwc3|udc|gadget|usb'
lspci -nnk | grep -A4 -i usb
```

### 有 UDC，但没有 `/dev/ttyGS0`

检查：

```bash
systemctl status mipad2-usb-serial.service
journalctl -b -u mipad2-usb-serial.service
dmesg | grep -Ei 'configfs|gadget|acm|ttyGS'
```

### Windows 没出现 COM 端口

先确认 Linux 端 service 已成功绑定 UDC，然后重新插拔 USB。若 Linux 端已经有 `/dev/ttyGS0` 且 UDC 状态正常，再检查 Windows 的设备管理器/驱动枚举。

## 5. 与 ADB 的关系

内核 USB Gadget/ConfigFS 提供的是底层能力；当前仓库直接维护的是 ACM serial 和 Ethernet gadget 辅助方案。ADB 是否可用还取决于用户态 adbd、FunctionFS/configfs 配置，不应把“DWC3 Device 模式正常”直接等同于“ADB 已配置完成”。
