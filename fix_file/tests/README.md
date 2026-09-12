# Mi Pad 2 硬件回归测试

这里的脚本用于在真机上快速确认当前内核是否还保留 Mi Pad 2 需要的关键设备节点和媒体拓扑。它们用于 **回归检查**，不是完整的硬件认证测试。

## `mipad2-hardware-smoke.sh`

默认模式是只读检查；只有显式设置 `MIPAD2_ACTIVE_CAMERA_TEST=1` 时，脚本才会额外发起摄像头 stream 测试。

当前 smoke test 会检查或提示以下项目：

- `/boot` 是否已挂载；
- Wi-Fi 无线接口；
- Bluetooth HCI 设备；
- ALSA 声卡；
- LCD backlight；
- touchscreen 输入设备名称；
- i915 DRM card 与 render node；
- Mi Pad 2 指示灯和触摸按键背光 LED；
- USB serial `/dev/ttyGS0`（未 attach 时只提示，不作为硬失败）；
- `/dev/media*` 与 `/dev/video*`；
- battery power-supply 节点；
- USB/Mains charger 节点（用于发现 BQ25890 路径）；
- ALS、加速度计、陀螺仪、磁力计、倾角/旋转等 IIO 设备；
- `/sys/class/udc` 下的 USB Device Controller；
- T4KA3 V4L2 subdev；
- DW9761/DW9719 VCM 及 `V4L2_CID_FOCUS_ABSOLUTE`；
- media graph 中的 T4KA3；
- T4KA3 controls 与 270° rotation metadata。

运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

输出中的含义：

- `OK`：本次启动中发现了脚本预期的节点/状态；
- `MISS`：预期项未发现，脚本最终会返回非 0；
- `INFO`：可选项或当前未启用的功能，不一定表示内核故障。

注意，`MISS /boot mounted` 可能只是你的发行版没有常驻挂载 `/boot`；某个 IIO 名称缺失也可能来自 userspace/ACPI 枚举差异。因此 smoke test 应与 `dmesg` 和实际功能测试一起看，而不是把单个 `MISS` 自动当成驱动回归。

### 可选主动摄像头检查

显式开启后，smoke script 会尝试对发现的 AtomISP video node 切换 input 并抓取少量帧：

```bash
sudo MIPAD2_ACTIVE_CAMERA_TEST=1 \
  sh fix_file/tests/mipad2-hardware-smoke.sh
```

这一步可能触发当前仍在开发中的 AtomISP 路径，所以默认不运行。

## `mipad2-camera-test.sh`

用法：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh front
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh both
```

省略参数时默认测试 `both`。

脚本会动态发现 AtomISP 的 video node，并在 **同一个 `v4l2-ctl` 打开周期**中完成格式设置和 stream。当前 AtomISP 路径不适合把格式设置和采集拆成两个独立的 `v4l2-ctl` 调用；重新打开节点后可能恢复传感器默认尺寸，进而造成错误的 pipeline/firmware 选择。

单次采集有超时保护。若某个传感器切换后驱动进入不可中断状态，不要连续重复测试；重启后先单独测试一个方向并保留日志。

推荐顺序：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

## `mipad2-camera-select.sh`

用于给普通 V4L2 应用选择当前 AtomISP input：

```bash
sudo sh fix_file/tests/mipad2-camera-select.sh rear
# 或
sudo sh fix_file/tests/mipad2-camera-select.sh front
```

它是 input 选择辅助工具，不会把 AtomISP 变成两个独立 `/dev/video*` 摄像头。

## 建议的回归时机

硬件相关改动后，至少在下面几种状态各跑一次 smoke test：冷启动后、相机使用后、耳机插拔后以及 suspend/resume 后。

出现问题时建议同时保存：

```bash
uname -a
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
media-ctl -p
v4l2-ctl --list-devices
dmesg > /tmp/mipad2-dmesg.txt
```

摄像头问题再补充：

```bash
dmesg | grep -Ei 'atomisp|ov5693|t4ka3|dw97'
```

这些脚本不会修改 BIOS、I2C 设备地址、音频 mixer 或系统电源策略。主动 camera test 只在显式启用时进行 V4L2 streaming。
