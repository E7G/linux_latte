# Mi Pad 2 硬件回归测试

本目录用于当前 Mi Pad 2 内核的真机回归，不是通用 Linux 硬件诊断工具。

## `mipad2-hardware-smoke.sh`

默认模式是 **只读 smoke test**。当前脚本实际检查的范围已经远大于早期文档所写的“摄像头、电池和 UDC”，包括：

- `/boot` 是否已挂载；
- Wi-Fi interface；
- Bluetooth HCI device；
- ALSA 声卡；
- LCD backlight；
- 触摸输入（包括 `FTSC1000:00`）；
- i915 DRM card / render node；
- `mipad2:rgb:indicator` 与 `mipad2:white:touch-buttons-backlight` LED；
- 可选的 `/dev/ttyGS0` USB serial gadget；
- `/dev/media*` 与 `/dev/video*`；
- Battery power-supply；
- BQ25890 charger 对应的 USB/Mains power-supply；
- `als`、`accel_3d`、`gyro_3d`、`magn_3d`、`incli_3d`、`dev_rotation` IIO 设备；
- 实际 UDC；
- T4KA3 V4L2 subdev；
- DW9761/DW9719 VCM、focus control；
- media graph 中的 T4KA3；
- T4KA3 controls 与 270° rotation metadata。

运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

输出含义：

- `OK`：脚本找到了当前预期的设备/接口；
- `INFO`：可选功能当前没有连接或脚本无法可靠识别，不直接判失败；
- `MISS`：当前预期的硬件接口缺失，脚本最终返回非 0。

“脚本找到设备”只表示枚举/接口层符合当前预期，不等于功能已经完成长时间稳定性验证。例如 ALSA 声卡存在并不能代替实际扬声器/麦克风测试，IIO 设备存在也不能代替传感器数据方向/精度测试。

### 主动摄像头 smoke test

`mipad2-hardware-smoke.sh` 默认不会开始摄像头采集。只有显式设置：

```bash
sudo MIPAD2_ACTIVE_CAMERA_TEST=1 \
    sh fix_file/tests/mipad2-hardware-smoke.sh
```

脚本才会对 AtomISP video node 的 input 0/1 做主动 stream 测试。

这一步可能触发当前仍在开发中的 AtomISP 问题，因此不建议把该环境变量长期写进自动开机任务。

## `mipad2-camera-test.sh`

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh [front|rear|both]
```

脚本会动态发现 AtomISP 的视频节点，并用同一次 `v4l2-ctl` 打开过程完成格式设置和采集。当前 AtomISP 路径中，格式设置与 stream 分成两次独立打开可能导致节点恢复到传感器默认尺寸，从而触发错误或固件 pipeline 选择问题。

建议先单独测试一个方向：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

单次采集有超时保护，但如果驱动进入不可中断状态，用户空间 timeout 不能保证恢复内核状态；遇到持续卡住时应重启后再继续测试。

## `mipad2-camera-select.sh`

普通 V4L2 应用如果需要先选择当前输入，可使用：

```bash
sudo sh fix_file/tests/mipad2-camera-select.sh rear
```

或：

```bash
sudo sh fix_file/tests/mipad2-camera-select.sh front
```

该脚本用于选择输入，不代表目标应用一定兼容 AtomISP 的媒体拓扑或格式协商方式。

## 推荐回归顺序

建议至少在以下场景运行 smoke test：

1. 冷启动后；
2. suspend/resume 后；
3. 摄像头使用后；
4. 耳机插拔/音频测试后；
5. USB gadget/串口启停后；
6. 修改 ACPI、电源、I2C、媒体、HID、无线或 defconfig 后。

基础检查：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

相机相关改动再额外执行：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

发生问题时建议一起保存：

```bash
uname -a
dmesg > /tmp/mipad2-dmesg.txt
sudo sh fix_file/tests/mipad2-hardware-smoke.sh | tee /tmp/mipad2-smoke.txt
media-ctl -p > /tmp/mipad2-media.txt 2>&1
v4l2-ctl --list-devices > /tmp/mipad2-v4l2.txt 2>&1
```

脚本本身不会修改 BIOS、I2C 寄存器、音频 mixer 或系统电源策略；但显式开启主动摄像头测试或运行 `mipad2-camera-test.sh` 会实际启动摄像头硬件和 AtomISP pipeline。


### Recovery safety test

Run the mocked recovery guard test with root privileges:

    sudo sh fix_file/tests/test-mipad2-recovery.sh

It stubs Timeshift, mounts, tar, and service-manager calls to verify detected root-device routing, snapshot-bound /boot archives, checksum/token validation, pre-reboot restoration, and fail-closed behavior without touching real filesystems.
