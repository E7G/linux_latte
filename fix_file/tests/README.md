# Mi Pad 2 硬件回归

脚本 `mipad2-hardware-smoke.sh` 只读检查摄像头节点、T4KA3、DW9761、电池和 UDC。

建议在冷启动、摄像头使用后、耳机插拔后以及每次 suspend/resume 后运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

该脚本不修改 BIOS、I2C、音频 mixer 或电源策略。
