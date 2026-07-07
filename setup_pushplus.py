from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path("config.json")


def main() -> int:
    if not CONFIG_PATH.exists():
        print("找不到 config.json，请在脚本目录运行。")
        return 1

    token = input("请粘贴 PushPlus token，然后回车: ").strip()
    if not token:
        print("token 为空，未修改配置。")
        return 1

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    config["pushplus_token"] = token

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("已写入 config.json。接下来会发送一条测试通知。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
