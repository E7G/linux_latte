# Mi Pad 2 硬件回归

脚本 `mipad2-hardware-smoke.sh` 只读检查摄像头节点、T4KA3、DW9761、电池和 UDC。

`mipad2-camera-test.sh [front|rear|both]` 会动态发现 AtomISP 的单一视频节点，
并用同一个 V4L2 文件描述符捕获指定摄像头一帧（默认 `both`）。AtomISP 的格式
设置必须和 stream 放在同一次 `v4l2-ctl` 调用中，否则重新打开节点后会回到
传感器默认尺寸并触发 `Failed to find a firmware binary`。

如果某个传感器切换后卡住，先只测试一个方向：

```bash
sudo sh fix_file/tests/mipad2-camera-test.sh rear
sudo sh fix_file/tests/mipad2-camera-test.sh front
```

单次采集最多等待 15 秒；若驱动进入不可中断状态，重启后再继续测试。

选择相机供普通 V4L2 应用使用：

```bash
sudo sh fix_file/tests/mipad2-camera-select.sh rear
```

建议在冷启动、摄像头使用后、耳机插拔后以及每次 suspend/resume 后运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
sudo sh fix_file/tests/mipad2-camera-test.sh
```

该脚本不修改 BIOS、I2C、音频 mixer 或电源策略。
