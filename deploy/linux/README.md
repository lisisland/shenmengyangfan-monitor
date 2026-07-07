# Linux 服务器部署

推荐系统：Ubuntu 22.04 / 24.04 或 Debian 12。

## 上传项目

在服务器上执行：

```bash
sudo mkdir -p /opt/shenmengyangfan
sudo chown -R "$USER:$USER" /opt/shenmengyangfan
```

把仓库里的这些文件上传到 `/opt/shenmengyangfan`：

```text
monitor.py
config.example.json
config_sleep_phone.example.json
```

脚本只用 Python 标准库，不需要安装第三方依赖。

然后在服务器上复制出本地配置：

```bash
cd /opt/shenmengyangfan
cp config.example.json config.json
cp config_sleep_phone.example.json config_sleep_phone.json
```

编辑 `config.json` / `config_sleep_phone.json`，填入自己的 PushPlus token 和群组编码。

## 手动测试

```bash
cd /opt/shenmengyangfan
python3 monitor.py --once
python3 monitor.py --test-notify
```

睡眠电话模式测试会拨电话并消耗 PushPlus 积分：

```bash
python3 monitor.py --config config_sleep_phone.json --test-large-notify
```

## systemd 常驻运行

微信模式：

```bash
sudo cp deploy/linux/shenmengyangfan-wechat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shenmengyangfan-wechat
sudo systemctl status shenmengyangfan-wechat
```

睡眠电话模式：

```bash
sudo cp deploy/linux/shenmengyangfan-phone.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shenmengyangfan-phone
sudo systemctl status shenmengyangfan-phone
```

不要同时启用两个模式，否则会重复通知。切换模式：

```bash
sudo systemctl stop shenmengyangfan-wechat
sudo systemctl start shenmengyangfan-phone
```

查看日志：

```bash
journalctl -u shenmengyangfan-wechat -f
journalctl -u shenmengyangfan-phone -f
```

停止：

```bash
sudo systemctl disable --now shenmengyangfan-wechat
sudo systemctl disable --now shenmengyangfan-phone
```
