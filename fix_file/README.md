[声音修复](./audio.md)

# WiFI
复制 `brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt` 到 `/lib/firmware/brcm` 文件夹下。
如果无效，重命名文件为 `brcmfmac4356-pcie.txt`。

# 蓝牙
复制 `BCM4356A2.hcd` 到 `/lib/firmware/brcm` 文件夹下。

# Intel Atom ISP
复制 `shisp_2401a0_v21.bin` 到 `/lib/firmware/` 文件夹下。

## 摄像头
OV5693 前置摄像头使用主线驱动。  
T4KA3 后置摄像头驱动已经直接集成到内核树，并在 `xiaomipad2_defconfig` 中作为模块启用。  
后摄的 DW9761 VCM 由 `dw9719` 驱动兼容支持，同样在默认配置中启用。  
`fix_file/latte-camera-t4ka3.patch` 保留为上游/回移参考，不再需要手工应用。

测试时先确认模块和媒体拓扑：

```bash
sudo modprobe atomisp
sudo modprobe ov5693
sudo modprobe t4ka3
sudo modprobe dw9719
dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97'
media-ctl -p
v4l2-ctl --list-devices
```

# 触摸屏底部按键
内容来自 [systemd/systemd-stable](https://github.com/systemd/systemd-stable/blob/v255-stable/hwdb.d/60-keyboard.hwdb)
添加 `/etc/udev/hwdb.d/60-keyboard.hwdb` 文件
```
###########################################################
# Xiaomi
###########################################################

# Fix mapping of menu / home / back capacitive buttons on bottom bezel
# Menu: LeftMeta + S   -> menu      (ignore LeftMeta, map S to menu)
# Home: LeftCtrl + Esc -> LeftMeta  (ignore LeftCtrl, map Esc to LeftMeta)
# Back: Backspace      -> back      (map backspace to back)
evdev:name:FTSC1000:00 2808:509C Keyboard:dmi:*:svnXiaomiInc:pnMipad2:*
 KEYBOARD_KEY_700e0=reserved	# LeftCtrl -> ignore
 KEYBOARD_KEY_700e3=reserved	# LeftMeta -> ignore
 KEYBOARD_KEY_70016=menu	# S -> menu
 KEYBOARD_KEY_70029=leftmeta	# Esc -> LeftMeta (Windows key / Win8 tablets home)
 KEYBOARD_KEY_7002a=back	# Backspace -> back

```

# 视频解码加速
arch上libva版本比较新降级即可，2.21.0-1版本可用。  
arch使用i965驱动解码单元，包名：libva-intel-driver  
https://github.com/intel/libva/issues/830

