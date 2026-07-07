from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import subprocess
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import winsound
except ImportError:
    winsound = None


APP_NAME = "深梦扬帆房源监控"
API_URL = "https://weapp.szajly.com/api/wechat/smyf/store/list"

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Referer": "https://servicewechat.com/wxb8f1a397304ee2ba/134/page-frame.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
        "MicroMessenger/7.0.20.1781 NetType/WIFI MiniProgramEnv/Windows "
        "WindowsWechat/WMPF WindowsWechat(0x63090a13)"
    ),
    "wxMiniAppId": "wxb8f1a397304ee2ba",
    "xweb_xhr": "1",
}


class PushServiceError(RuntimeError):
    def __init__(self, service_name: str, code: Any, msg: str) -> None:
        super().__init__(f"{service_name} 返回异常: code={code}, msg={msg}")
        self.service_name = service_name
        self.code = code
        self.msg = msg


@dataclass(frozen=True)
class Alert:
    check_in_date: str
    store_id: int | str
    store_name: str
    area_name: str
    remain: int
    near_metro: str
    near_station: str

    def key(self) -> tuple[str, str]:
        return self.check_in_date, str(self.store_id)

    def line(self) -> str:
        metro = " ".join(x for x in [self.near_metro, self.near_station] if x)
        suffix = f" | {metro}" if metro else ""
        return (
            f"{self.check_in_date} | {self.area_name} | {self.store_name} "
            f"| 剩余 {self.remain} 间{suffix}"
        )


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        config = json.load(f)
    return config


def log(message: str, config: dict[str, Any] | None = None) -> None:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {message}"
    print(line, flush=True)

    if not config or not config.get("log_file"):
        return
    log_path = Path(config["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def build_dates(config: dict[str, Any]) -> list[str]:
    configured = [str(x).strip() for x in config.get("check_in_dates", []) if str(x).strip()]
    if configured:
        return configured

    start_after_days = int(config.get("start_after_days", 0))
    days_ahead = int(config.get("days_ahead", 15))
    today = dt.date.today()
    return [
        (today + dt.timedelta(days=start_after_days + i)).isoformat()
        for i in range(days_ahead)
    ]


def parse_hhmm(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def time_in_window(now_minutes: int, start_minutes: int, end_minutes: int) -> bool:
    if start_minutes <= end_minutes:
        return start_minutes <= now_minutes <= end_minutes
    return now_minutes >= start_minutes or now_minutes <= end_minutes


def current_interval_seconds(config: dict[str, Any]) -> int:
    normal_interval = int(config.get("interval_seconds", 30))
    now = dt.datetime.now()
    now_minutes = now.hour * 60 + now.minute

    for window in config.get("hot_windows", []):
        try:
            start = parse_hhmm(str(window["start"]))
            end = parse_hhmm(str(window["end"]))
            if time_in_window(now_minutes, start, end):
                return int(window.get("interval_seconds", normal_interval))
        except (KeyError, TypeError, ValueError):
            continue

    return normal_interval


def describe_hot_windows(config: dict[str, Any]) -> str:
    parts = []
    for window in config.get("hot_windows", []):
        try:
            name = str(window.get("name") or "热点")
            parts.append(
                f"{name} {window['start']}-{window['end']} 每 {int(window['interval_seconds'])} 秒"
            )
        except (KeyError, TypeError, ValueError):
            continue
    return "；".join(parts)


def build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    headers.update({str(k): str(v) for k, v in config.get("headers", {}).items() if v})
    return headers


def fetch_store_list(check_in_date: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "checkInTime": check_in_date,
            "companyUrl": config.get("company_url", "AJLY"),
        }
    )
    url = f"{API_URL}?{query}"
    request = urllib.request.Request(url, headers=build_headers(config), method="GET")

    with urllib.request.urlopen(request, timeout=int(config.get("request_timeout_seconds", 15))) as response:
        raw = response.read()

    payload = json.loads(raw.decode("utf-8"))
    if payload.get("code") != 200:
        raise RuntimeError(f"接口返回异常: {payload}")

    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError(f"接口 data 不是列表: {payload}")
    return data


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def store_matches(store: dict[str, Any], config: dict[str, Any]) -> bool:
    store_ids = {str(x).strip() for x in config.get("store_ids", []) if str(x).strip()}
    store_keywords = [str(x).strip() for x in config.get("store_name_keywords", []) if str(x).strip()]
    area_keywords = [str(x).strip() for x in config.get("area_keywords", []) if str(x).strip()]

    store_id = str(store.get("storeId", "")).strip()
    store_name = str(store.get("storeName") or "")
    area_name = str(store.get("areaName") or "")

    if store_ids and store_id not in store_ids:
        return False
    if store_keywords and not any(keyword in store_name for keyword in store_keywords):
        return False
    if area_keywords and not any(keyword in area_name for keyword in area_keywords):
        return False
    return True


def collect_alerts(check_in_date: str, stores: list[dict[str, Any]], config: dict[str, Any]) -> list[Alert]:
    min_remain = int(config.get("min_remain", 1))
    alerts: list[Alert] = []

    for store in stores:
        if not store_matches(store, config):
            continue

        remain = as_int(store.get("houseRemain"), 0)
        if remain < min_remain:
            continue

        alerts.append(
            Alert(
                check_in_date=check_in_date,
                store_id=store.get("storeId", ""),
                store_name=str(store.get("storeName") or ""),
                area_name=str(store.get("areaName") or ""),
                remain=remain,
                near_metro=str(store.get("nearMetroName") or ""),
                near_station=str(store.get("nearStationName") or ""),
            )
        )
    return alerts


def should_notify(
    alert: Alert,
    previous_remain: dict[tuple[str, str], int],
    last_notified_at: dict[tuple[str, str], float],
    config: dict[str, Any],
) -> bool:
    key = alert.key()
    before = previous_remain.get(key, 0)
    if before <= 0:
        return True
    if alert.remain > before:
        return True

    repeat_minutes = float(config.get("repeat_notify_minutes", 5))
    if repeat_minutes <= 0:
        return False

    last = last_notified_at.get(key, 0)
    return (time.time() - last) >= repeat_minutes * 60


def should_voice_call(
    alert: Alert,
    previous_remain: dict[tuple[str, str], int],
    last_voice_called_at: dict[str, float],
    config: dict[str, Any],
) -> bool:
    if not config.get("voice_call_enabled", True):
        return False

    min_remain = int(config.get("voice_call_min_remain", 1))
    if min_remain <= 0 or alert.remain < min_remain:
        return False

    before = previous_remain.get(alert.key(), 0)
    if before > 0:
        return False

    cooldown_minutes = float(config.get("voice_call_cooldown_minutes", 3))
    if cooldown_minutes <= 0:
        return True

    last = last_voice_called_at.get("global", 0)
    return (time.time() - last) >= cooldown_minutes * 60


def send_windows_notification(title: str, message: str) -> None:
    if winsound is None:
        return

    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
    message_b64 = base64.b64encode(message.encode("utf-8")).decode("ascii")
    ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$title = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{title_b64}'))
$message = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{message_b64}'))
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = $title
$notify.BalloonTipText = $message
$notify.Visible = $true
$notify.ShowBalloonTip(10000)
Start-Sleep -Seconds 12
$notify.Dispose()
"""
    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def post_json(url: str, payload: dict[str, Any], timeout: int = 15) -> str:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json;charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_push_response(service_name: str, response_text: str) -> None:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return

    code = payload.get("code")
    if code in (0, 200):
        return

    msg = payload.get("msg") or payload.get("message") or response_text
    raise PushServiceError(service_name, code, str(msg))


def simple_push_text(message: str) -> str:
    simplified = message.replace("|", "，")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"发现时间：{now}\n发现可申请房源，请马上打开小程序查看。\n{simplified}"


def post_form(url: str, payload: dict[str, Any], timeout: int = 15) -> str:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def as_nonempty_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def pushplus_target_payload(
    config: dict[str, Any],
    *,
    voice: bool = False,
) -> dict[str, str]:
    if voice:
        topic = str(config.get("pushplus_voice_topic") or "").strip()
        friend_tokens = as_nonempty_list(config.get("pushplus_voice_friend_tokens", []))
    else:
        topic = str(config.get("pushplus_topic") or "").strip()
        friend_tokens = as_nonempty_list(config.get("pushplus_friend_tokens", []))

    # PushPlus 官方说明：topic 优先于 to，不要同时填写。
    if topic:
        return {"topic": topic}
    if friend_tokens:
        return {"to": ",".join(friend_tokens)}
    return {}


def send_pushplus(title: str, message: str, config: dict[str, Any]) -> None:
    token = str(config.get("pushplus_token") or "").strip()
    if not token:
        return
    timeout = int(config.get("request_timeout_seconds", 15))
    payload = {
        "token": token,
        "title": title,
        "content": message,
        "template": "txt",
    }
    payload.update(pushplus_target_payload(config))
    try:
        response_text = post_json("https://www.pushplus.plus/send", payload, timeout=timeout)
        parse_push_response("PushPlus", response_text)
    except PushServiceError as exc:
        if exc.code != 999 or not config.get("pushplus_retry_simple", True):
            raise
        log("PushPlus 返回 999，改用简化内容重试一次。", config)
        response_text = post_json(
            "https://www.pushplus.plus/send",
            {
                "token": token,
                "title": "深梦扬帆房源提醒",
                "content": simple_push_text(message),
                "template": "txt",
                **pushplus_target_payload(config),
            },
            timeout=timeout,
        )
        parse_push_response("PushPlus简化重试", response_text)


def send_pushplus_voice(title: str, message: str, config: dict[str, Any]) -> None:
    token = str(config.get("pushplus_token") or "").strip()
    if not token:
        return
    payload = {
        "token": token,
        "title": title,
        "content": message,
        "template": "txt",
        "channel": "voice",
    }
    payload.update(pushplus_target_payload(config, voice=True))
    response_text = post_json(
        "https://www.pushplus.plus/send",
        payload,
        timeout=int(config.get("request_timeout_seconds", 15)),
    )
    parse_push_response("PushPlus语音电话", response_text)


def send_serverchan(title: str, message: str, config: dict[str, Any]) -> None:
    sendkey = str(config.get("serverchan_sendkey") or "").strip()
    if not sendkey:
        return
    url = f"https://sctapi.ftqq.com/{urllib.parse.quote(sendkey)}.send"
    response_text = post_form(
        url,
        {"title": title, "desp": message},
        timeout=int(config.get("request_timeout_seconds", 15)),
    )
    parse_push_response("Server酱", response_text)


def send_webhook(title: str, message: str, alerts: list[Alert], config: dict[str, Any]) -> None:
    webhook_url = str(config.get("webhook_url") or "").strip()
    if not webhook_url:
        return
    post_json(
        webhook_url,
        {
            "title": title,
            "content": message,
            "alerts": [alert.__dict__ for alert in alerts],
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        },
        timeout=int(config.get("request_timeout_seconds", 15)),
    )


def send_remote_notifications(
    title: str,
    message: str,
    alerts: list[Alert],
    config: dict[str, Any],
) -> None:
    send_pushplus(title, message, config)
    send_serverchan(title, message, config)
    send_webhook(title, message, alerts, config)


def build_voice_title(alerts: list[Alert], config: dict[str, Any]) -> str:
    if not alerts:
        return f"{APP_NAME}发现可申请房源，请马上查看"

    top_alert = max(alerts, key=lambda alert: alert.remain)
    month_day = top_alert.check_in_date[5:].replace("-", "月") + "日"
    return (
        f"深梦扬帆房源提醒，{month_day}，{top_alert.store_name}"
        f"，剩余{top_alert.remain}间，请马上查看"
    )


def notify(
    alerts: list[Alert],
    config: dict[str, Any],
    voice_alerts: list[Alert] | None = None,
) -> bool:
    if not alerts:
        return True

    voice_alerts = voice_alerts or []
    urgent = bool(voice_alerts)
    title_prefix = "重点提醒 " if urgent else ""
    title = f"{title_prefix}{APP_NAME}: 发现 {len(alerts)} 条可申请房源"
    message = "\n".join(alert.line() for alert in alerts[:10])
    if len(alerts) > 10:
        message += f"\n... 还有 {len(alerts) - 10} 条"

    log("触发提醒:\n" + message, config)

    if config.get("windows_notification", True):
        send_windows_notification(title, message)

    try:
        send_remote_notifications(title, message, alerts, config)
        if voice_alerts and config.get("voice_call_enabled", True):
            voice_title = build_voice_title(voice_alerts, config)
            log(f"语音电话提醒：{voice_title}", config)
            send_pushplus_voice(voice_title, message, config)
    except Exception as exc:
        log(f"推送失败: {exc}", config)
        return False

    return True


def write_latest_available(alerts: list[Alert], config: dict[str, Any]) -> None:
    latest_file = str(config.get("latest_available_file") or "").strip()
    if not latest_file:
        return

    path = Path(latest_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not alerts:
        content = f"[{now}] 当前没有检测到可用房源。\n"
    else:
        lines = [f"[{now}] 当前检测到 {len(alerts)} 条可用房源："]
        lines.extend(alert.line() for alert in alerts)
        content = "\n".join(lines) + "\n"

    path.write_text(content, encoding="utf-8")


def run_once(
    config: dict[str, Any],
    previous_remain: dict[tuple[str, str], int],
    last_notified_at: dict[tuple[str, str], float],
    last_voice_called_at: dict[str, float],
) -> int:
    dates = build_dates(config)
    total_stores = 0
    current_alerts: list[Alert] = []
    notify_alerts: list[Alert] = []
    voice_alerts: list[Alert] = []
    current_remain: dict[tuple[str, str], int] = {}

    for check_in_date in dates:
        stores = fetch_store_list(check_in_date, config)
        total_stores += len(stores)
        alerts = collect_alerts(check_in_date, stores, config)

        for store in stores:
            if not store_matches(store, config):
                continue
            key = (check_in_date, str(store.get("storeId", "")))
            current_remain[key] = as_int(store.get("houseRemain"), 0)

        for alert in alerts:
            current_alerts.append(alert)
            if should_notify(alert, previous_remain, last_notified_at, config):
                notify_alerts.append(alert)
                if should_voice_call(alert, previous_remain, last_voice_called_at, config):
                    voice_alerts.append(alert)

    write_latest_available(current_alerts, config)
    notify_ok = notify(notify_alerts, config, voice_alerts=voice_alerts)

    now_ts = time.time()
    if notify_ok:
        for alert in notify_alerts:
            last_notified_at[alert.key()] = now_ts
        if voice_alerts:
            last_voice_called_at["global"] = now_ts
    elif notify_alerts:
        log("本轮推送未成功，下一轮会继续尝试。", config)

    # Update state after notifying, so 0 -> positive transitions are not missed.
    previous_remain.clear()
    previous_remain.update(current_remain)

    if notify_alerts:
        return len(notify_alerts)
    if current_alerts:
        log(f"当前仍有 {len(current_alerts)} 条可用房源；未到重复提醒间隔。", config)
        return len(current_alerts)

    checked = len(dates)
    log(f"本轮无房源；已查 {checked} 个日期，约 {total_stores} 条门店记录。", config)
    return 0


def run_loop(config: dict[str, Any], once: bool = False) -> None:
    previous_remain: dict[tuple[str, str], int] = {}
    last_notified_at: dict[tuple[str, str], float] = {}
    last_voice_called_at: dict[str, float] = {}

    log(f"{APP_NAME}启动。按 Ctrl+C 停止。", config)
    log(f"监控日期: {', '.join(build_dates(config))}", config)
    log(f"常规轮询间隔: {int(config.get('interval_seconds', 30))} 秒。", config)
    hot_windows = describe_hot_windows(config)
    if hot_windows:
        log(f"热点时段: {hot_windows}。", config)

    while True:
        try:
            run_once(config, previous_remain, last_notified_at, last_voice_called_at)
        except KeyboardInterrupt:
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            log(f"网络请求失败: {exc}", config)
        except Exception as exc:
            log(f"本轮执行异常: {exc}", config)
            if config.get("debug", False):
                log(traceback.format_exc(), config)

        if once:
            return
        time.sleep(current_interval_seconds(config))


def test_notify(config: dict[str, Any]) -> None:
    check_in_date = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    sample = Alert(
        check_in_date=check_in_date,
        store_id=66,
        store_name="[模拟] 莲塘仙湖店",
        area_name="罗湖区",
        remain=1,
        near_metro="地铁2号线",
        near_station="仙湖路",
    )
    notify([sample], config)


def test_large_notify(config: dict[str, Any]) -> None:
    check_in_date = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    sample = Alert(
        check_in_date=check_in_date,
        store_id=82,
        store_name="[模拟电话] 精茂花园店",
        area_name="盐田区",
        remain=max(1, int(config.get("voice_call_min_remain", 1))),
        near_metro="地铁2号线",
        near_station="盐田港西",
    )
    notify([sample], config, voice_alerts=[sample])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--config", default="config.json", help="配置文件路径，默认 config.json")
    parser.add_argument("--once", action="store_true", help="只检查一轮后退出")
    parser.add_argument("--test-notify", action="store_true", help="发送一条测试通知后退出")
    parser.add_argument("--test-large-notify", action="store_true", help="发送大量房源微信+语音电话测试通知后退出")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)

    if args.test_notify:
        test_notify(config)
        return 0
    if args.test_large_notify:
        test_large_notify(config)
        return 0

    try:
        run_loop(config, once=args.once)
    except KeyboardInterrupt:
        log("已停止。", config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
