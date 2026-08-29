# Mi Pad 2 RT5659 音频

当前仓库提供 `mipad2-alsa-ucm`，由 PipeWire/WirePlumber 通过 UCM 管理扬声器、耳机、内置麦克风和耳麦麦克风。

## 安装

```bash
makepkg -si -f fix_file/packages/mipad2-alsa-ucm
```

安装后重启 PipeWire，或重新登录：

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

不要再执行旧版文档中的 `amixer -c0 cset "name='Amp Input1'" Right`；右扬声器路由已由 UCM 的 `Speaker` 配置接管。

## 验证

```bash
wpctl status
wpctl set-profile @DEFAULT_AUDIO_SINK@ pro-audio
speaker-test -D default -c 2 -t pink
arecord -D default -f S16_LE -c 2 -r 48000 /tmp/mipad2-mic.wav
```

插拔耳机时，声卡应出现 `cht-bsw-rt5659 Headset` 的 jack 状态变化；若恢复 suspend 后无声，先查看 `journalctl -b -u wireplumber` 和 `dmesg | grep -i rt5659`。
