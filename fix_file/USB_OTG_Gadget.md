# Mi Pad 2 USB device mode / Gadget

Mi Pad 2 的 USB device mode 负责让平板以 USB 设备身份连接电脑。CDC ACM 串口、USB 网络等功能都建立在 UDC + USB Gadget/ConfigFS 之上。

当前内核已经在 `xiaomipad2_defconfig` 中启用 DWC3 PCI dual-role、USB Gadget、ConfigFS serial/ACM 和 USB serial console 相关支持。**内核配置已经具备能力，不代表固件一定会把控制器暴露成可用 UDC。**

## 先检查，不要先改 BIOS

启动当前内核后先执行：

```bash
ls -la /sys/class/udc/
```

如果能看到实际 UDC，优先直接测试当前 USB 串口方案，不需要为了“保险”去改 UEFI 变量。

也可以检查：

```bash
dmesg | grep -Ei 'dwc3|udc|gadget|usb'
```

只有在 `/sys/class/udc/` 始终为空，并且确认问题确实是 Mi Pad 2 固件的 OTG 模式后，再考虑下面的 BIOS 设置。

## 当前推荐：USB CDC ACM 串口

仓库提供 `mipad2-usb-serial`。它会创建一个 CDC ACM gadget，平板侧使用 `/dev/ttyGS0`；当前内核启用了 `CONFIG_U_SERIAL_CONSOLE`，因此 gadget 激活后还可以注册为内核 console，并重放 USB 枚举前积累的 printk ring buffer。

Arch / `makepkg` 环境：

```bash
cd fix_file/packages/mipad2-usb-serial
makepkg -si
sudo systemctl enable --now mipad2-usb-serial.service
```

验证：

```bash
systemctl status mipad2-usb-serial.service
ls -l /dev/ttyGS0
ls -la /sys/class/udc/
```

Windows 主机通常会显示 **Mi Pad 2 USB Serial** 对应的 COM 口，可按 `115200 8N1` 使用。

> `mipad2-usb-serial` 与旧的 `mipad2-usb-gadget` 冲突，并会替代后者。原因是同一个 UDC 不能同时被旧的 legacy `g_ether` 和当前 ACM ConfigFS gadget 绑定。当前仓库推荐 USB 串口作为无 Wi-Fi 时的早期调试/恢复路径。

## BIOS / UEFI：USB OTG Support

部分 Mi Pad 2 固件需要把 `USB OTG Support` 设置为 **PCI Mode**，Linux 才能按当前 DWC3 PCI 路径获得可用 UDC。

如果使用解锁了完整选项的 BIOS，可直接把：

```text
USB OTG Support = PCI Mode
```

原厂 BIOS 中，本项目历史测试使用 Setup 变量偏移 `0x2a2`：

| 值 | 含义 |
| --- | --- |
| `0x0` | Disable |
| `0x1` | PCI Mode |
| `0x2` | ACPI Mode |
| `0x3` | AUTO Mode（在该固件上表现接近 ACPI Mode） |

历史做法是从 `0x3` 改成 `0x1`。

### 风险提示

直接修改 UEFI Setup 变量属于固件级操作。**偏移只适用于已经核对过的 Mi Pad 2 固件版本，不应照搬到其他设备或未知 BIOS 版本。** 写错 Setup 变量可能造成无法启动、USB 行为异常，甚至需要外部恢复手段。

在修改前至少应：

- 确认设备确实是 Xiaomi Mi Pad 2 / latte；
- 记录修改前的原始值；
- 确保自己有可用的 EFI Shell/启动介质和恢复方案；
- 只修改目标字节，不批量写入未知变量。

可用工具及历史命令：

| 工具 | 示例 |
| --- | --- |
| [`setup_var.efi`](https://github.com/datasone/setup_var.efi) | EFI Shell：`setup_var.efi Setup:0x2a2=0x1` |
| 带 `setup_var` 模块的 GRUB | GRUB Shell：`setup_var 0x2a2 0x1` |
| RU.EFI | 仅建议在确认变量布局后手工修改；本项目不把旧的按键导航步骤视为已验证流程 |

修改后重新启动 Linux，再以 `/sys/class/udc/` 是否出现实际 UDC 为准，不要仅凭 BIOS 选项名称判断是否成功。

## 常见问题

### `/sys/class/udc/` 为空

先看 DWC3 是否枚举：

```bash
lspci -nnk | grep -A4 -Ei 'USB|DWC3'
dmesg | grep -Ei 'dwc3|udc|gadget|usb'
```

如果控制器存在但没有 UDC，再检查 BIOS OTG 模式和当前内核是否确实使用 `xiaomipad2_defconfig`。

### 服务启动失败，提示 UDC busy

检查是否已有 gadget/legacy gadget 占用：

```bash
lsmod | grep -E 'g_ether|g_serial|g_multi'
find /sys/kernel/config/usb_gadget -maxdepth 2 -type f -name UDC -print -exec cat {} \;
```

不要同时启用旧 `mipad2-usb-gadget` 和新 `mipad2-usb-serial`。

### 电脑没有看到串口

平板侧依次确认：

```bash
systemctl status mipad2-usb-serial.service
ls -l /dev/ttyGS0
cat /sys/kernel/config/usb_gadget/mipad2/UDC 2>/dev/null
```

再更换数据线/USB 口并检查主机设备管理器或 `dmesg`。充电线不一定包含数据线芯。
