# Mi Pad 2 RT5659 音频

当前仓库提供 `mipad2-alsa-ucm`，由 PipeWire/WirePlumber 通过 UCM 管理扬声器、耳机、内置麦克风和耳麦麦克风。

这部分由 **内核声卡驱动 + userspace UCM 配置**共同完成。仅看到 ALSA 声卡不代表 PipeWire 的路由一定正确；反过来，UCM 包也不能修复内核没有枚举出声卡的问题。

## 安装

`makepkg` 需要在包含 `PKGBUILD` 的目录中运行：

```bash
cd fix_file/packages/mipad2-alsa-ucm
makepkg -si
```

安装后重启 PipeWire/WirePlumber，或重新登录：

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

不要再执行旧版文档中的：

```bash
amixer -c0 cset "name='Amp Input1'" Right
```

当前右扬声器路由应由 UCM 的 `Speaker` 配置接管，手工长期写 mixer 值反而会让问题更难复现。

## 验证

先确认内核已经枚举 ALSA 声卡：

```bash
cat /proc/asound/cards
aplay -l
arecord -l
```

再检查 PipeWire/WirePlumber：

```bash
wpctl status
```

播放与录音测试：

```bash
speaker-test -D default -c 2 -t pink
arecord -D default -f S16_LE -c 2 -r 48000 /tmp/mipad2-mic.wav
```

插拔耳机时，声卡应出现 `cht-bsw-rt5659 Headset` 的 jack 状态变化。

## 出问题时

如果冷启动正常、suspend/resume 后无声，优先保留当次启动的日志：

```bash
journalctl --user -b -u wireplumber
journalctl -b | grep -Ei 'pipewire|wireplumber|alsa'
dmesg | grep -Ei 'rt5659|cht|sst|audio'
```

同时运行通用硬件检查：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

硬件 smoke test 只确认 ALSA 声卡等基础节点是否存在，不会修改 mixer，也不能替代实际左右声道、耳机和麦克风测试。
