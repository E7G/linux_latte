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

默认测试 1280×720 `YU12`。可用 `MIPAD2_CAMERA_PIXEL_FORMAT=NV12` 或 `YUYV` 覆盖格式，例如：

```bash
sudo MIPAD2_CAMERA_PIXEL_FORMAT=NV12 sh fix_file/tests/mipad2-camera-test.sh both
sudo MIPAD2_CAMERA_SWITCH_CYCLES=6 sh fix_file/tests/mipad2-camera-test.sh both
```

脚本会检查本次采集期间是否新增 AtomISP CSS 队列错误，并在退出时恢复运行前选中的摄像头 input；如无权限读取 `dmesg`，仍会验证采集命令与非空帧，但跳过内核日志判定。

建议先单独测试一个方向：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

单次采集有超时保护，但如果驱动进入不可中断状态，用户空间 timeout 不能保证恢复内核状态；遇到持续卡住时应重启后再继续测试。

## OV5693 前摄 OTP 校准

Host parser 回归（无需平板/摄像头）：运行
python3 fix_file/tests/mipad2-ov5693-otp-parser-test.py

fixture 从内核源抽取实际解析函数，逐值检查 module/AWB 分组与回退布局，并验证 CRC 正向及损坏 CRC 反向。


读取 416-byte raw OTP，并检查 Android 格式解析后的 320-byte 校准 NVMEM（CRC16/IBM 与固定 AF block）：

```bash
sudo sh fix_file/tests/mipad2-ov5693-otp-test.sh
```

此项验证设备 OTP 的结构与校验，不替代目视图像、色彩/白平衡和 AtomISP 实际消费校准数据的验收。

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

## 传感器方向矩阵

`mipad2-sensor-orientation-audit.sh` 检查 Xiaomi/Mipad2 DMI 限定下，Mi Pad 2 `8086:0001` 原始三轴传感器 hub 和 Windows 备份识别的 `8086:0002` ISS hub，为加速度计/重力、陀螺仪和磁力计导出 Android HAL 对应的 `diag(-1, 1, -1)` IIO `mount_matrix`；同时检查 rotation-from-north HID 单位指数映射。硬件 smoke test 验证实际 sysfs 矩阵值和 compass rotation scale。

这只验证方向元数据和接口，不替代真机方向响应测试。安装 `iio-sensor-proxy` 后运行 `monitor-sensor --accel`，正面朝向用户依次旋转到竖屏、左右横屏和倒置竖屏；再于冷启动和 suspend/resume 后重复。记录四个朝向，确认没有 90°/180° 偏差或频繁抖动。

## 防息屏前置

运行 Wi-Fi、USB gadget/串口、相机等硬件回归前，先关闭自动息屏并回读状态：

sudo mp2-test-no-idle enable
sudo mp2-test-no-idle status

status 只有在 inhibitor 为 active 且 idle-delay=0、idle-dim=false、AC/电池 sleep policy 均为 nothing 时才返回 0 并打印 PASS；否则返回非零，不要继续硬件测试。全部测试结束后用 sudo mp2-test-no-idle disable 恢复此前电源设置。

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

## T4KA3 后摄 OTP / Android 标定布局

`mipad2-t4ka3-otp-calibrated-test.py` 校验 578-byte raw OTP 四组校验和，并逐字节比对 544-byte AtomISP 格式与 Xiaomi Android `dw9761_otp_format()` 布局（含 AF、LSC、AWB、CRC16/IBM）。新内核启动后运行：

```bash
sudo python3 fix_file/tests/mipad2-t4ka3-otp-calibrated-test.py
```

离线回归可传入 raw 与 calibrated 两个文件路径；应通过 `OK` 且字节完全相同。它验证布局/校验，不代表图像色彩或 ISP 画质验收。
