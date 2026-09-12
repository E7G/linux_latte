# Mi Pad 2 RT5659 / TFA9890 音频

当前仓库提供 `mipad2-alsa-ucm`，用于 Xiaomi Mi Pad 2 的 RT5659 codec 与双 TFA9890 功放用户空间路由。PipeWire/WirePlumber 或其他支持 ALSA UCM2 的音频栈应通过该 UCM 配置管理扬声器、耳机、内置麦克风和耳麦麦克风。

这部分不是“再打一份内核音频补丁”：当前重点是让用户空间使用与内核驱动匹配的 UCM profile。

## 安装

### Arch / makepkg

从包目录执行 `makepkg`：

```bash
cd fix_file/packages/mipad2-alsa-ucm
makepkg -si
```

不要使用旧文档中的：

```text
makepkg -si -f fix_file/packages/mipad2-alsa-ucm
```

`makepkg` 不是用最后一个路径参数选择 PKGBUILD，应该进入包目录后执行。

安装后重新登录，或重启用户音频服务：

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

如果你的发行版不使用 PipeWire/WirePlumber，只要它支持 ALSA UCM2，也可以按其音频服务方式重新加载配置。UCM 文件最终安装到 `/usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/`。

## 不要再使用旧的固定 mixer 修复

不要再执行早期文档里的：

```text
amixer -c0 cset "name='Amp Input1'" Right
```

右扬声器和其他播放/录音路径已经由 UCM 的设备/verb 配置接管。额外固定 mixer 值可能与 WirePlumber/PipeWire 的路由切换互相覆盖。

## 验证

先确认内核声卡和用户空间设备：

```bash
cat /proc/asound/cards
wpctl status
```

测试左右声道：

```bash
speaker-test -D default -c 2 -t pink
```

测试录音：

```bash
arecord -D default -f S16_LE -c 2 -r 48000 /tmp/mipad2-mic.wav
aplay /tmp/mipad2-mic.wav
```

插拔耳机时，应能看到 RT5659 headset jack 状态变化，并由用户空间切换到相应路径。

## 排错

先确认当前 UCM 文件确实已经安装：

```bash
find /usr/share/alsa/ucm2 -path '*cht-bsw-rt5659*' -maxdepth 5 -type f -print
```

然后检查：

```bash
journalctl --user -b -u wireplumber
journalctl --user -b -u pipewire

dmesg | grep -Ei 'rt5659|tfa9890|snd|audio'
```

如果只有 suspend/resume 后失声，请把它当成电源管理回归问题记录：同时保存 suspend 前后的 `wpctl status`、`/proc/asound/cards` 和相关 `dmesg`，不要先用固定 mixer 命令掩盖问题。

建议每次修改音频、电源管理或 suspend/resume 相关代码后，同时运行：

```bash
sudo sh fix_file/tests/mipad2-hardware-smoke.sh
```

该 smoke test 会检查系统是否仍然枚举出 ALSA 声卡，但它不会代替实际扬声器、耳机和麦克风试听/录音测试。
