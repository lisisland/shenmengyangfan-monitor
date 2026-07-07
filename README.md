# 深梦扬帆房源监控

一个用于监控安居乐寓「深梦扬帆」活动房源余量的 Python 脚本。它会定时查询可申请入住日期内的房源列表，发现可申请房源时通过 PushPlus / Server 酱 / Webhook 推送通知。

项目只做「监控和通知」，不会自动提交申请，也不会自动抢房。

## 功能

- 只监控实际可申请窗口：默认 `今天+5`、`今天+6`、`今天+7` 三天。
- 支持热点时段加速轮询：午夜新增第 7 天、白天退房/释放高峰等。
- 支持 PushPlus 微信通知，可配置群组 `topic` 做多人通知。
- 支持睡眠电话模式：发现房源时额外触发 PushPlus 语音电话。
- 支持 Windows 本地弹窗响铃。
- 支持 Linux 服务器 `systemd` 常驻运行，适合 24 小时监控。
- 支持 PushPlus 失败后的简化内容重试。
- 无第三方 Python 依赖，只使用标准库。

## 工作原理

脚本轮询深梦扬帆房源列表接口：

```text
https://weapp.szajly.com/api/wechat/smyf/store/list
```

当返回数据中的 `houseRemain > 0` 时触发通知。通知内容包含入住日期、区、门店、剩余房源数和附近地铁信息。

## 快速开始

准备配置文件：

```bash
cp config.example.json config.json
cp config_sleep_phone.example.json config_sleep_phone.json
```

编辑 `config.json`，至少填写 PushPlus token：

```json
{
  "pushplus_token": "YOUR_PUSHPLUS_TOKEN"
}
```

如果要群发给 PushPlus 群组，填写群组编码：

```json
{
  "pushplus_topic": "YOUR_GROUP_TOPIC"
}
```

运行一次检查：

```bash
python monitor.py --once
```

持续运行微信模式：

```bash
python monitor.py --config config.json
```

睡眠电话模式：

```bash
python monitor.py --config config_sleep_phone.json
```

发送测试通知：

```bash
python monitor.py --test-notify
```

发送语音电话测试通知，会消耗 PushPlus 积分：

```bash
python monitor.py --config config_sleep_phone.json --test-large-notify
```

## Windows

双击：

```text
run_monitor.bat
```

睡眠电话模式：

```text
run_monitor_sleep_phone.bat
```

测试通知：

```text
test_notify.bat
test_voice_notify.bat
```

## Linux 服务器

见 [deploy/linux/README.md](deploy/linux/README.md)。

推荐部署为 `systemd` 服务，电脑关机后服务器仍会 24 小时运行。

## 配置说明

常用字段：

```json
{
  "start_after_days": 5,
  "days_ahead": 3,
  "interval_seconds": 30,
  "min_remain": 1,
  "repeat_notify_minutes": 5,
  "voice_call_enabled": false,
  "voice_call_min_remain": 1,
  "voice_call_cooldown_minutes": 3,
  "pushplus_token": "",
  "pushplus_topic": "",
  "pushplus_friend_tokens": [],
  "pushplus_voice_topic": "",
  "pushplus_voice_friend_tokens": []
}
```

- `start_after_days` / `days_ahead`: 默认只查 5-7 天后的三天。
- `hot_windows`: 热点时段加速轮询配置。
- `pushplus_topic`: PushPlus 群组编码，适合多人微信通知。
- `pushplus_friend_tokens`: PushPlus 好友令牌列表，不填群组时可用。
- `voice_call_enabled`: 是否开启语音电话模式。
- `pushplus_voice_topic`: 语音电话群组编码，默认空，避免误给多人打电话扣积分。
- `store_ids`、`store_name_keywords`、`area_keywords`: 可用于过滤门店。

## 安全

不要把这些文件提交到公开仓库：

```text
config.json
config_sleep_phone.json
logs/
server_package.zip
```

仓库已通过 `.gitignore` 忽略它们。公开仓库只保留 `*.example.json` 示例配置。

## 免责声明

本项目仅用于个人学习和信息提醒，不包含自动提交、自动预约或绕过业务流程的能力。请合理设置轮询频率，遵守目标服务的使用规则。
