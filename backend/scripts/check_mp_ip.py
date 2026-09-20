"""检查当前公网出口 IP 是否变化（微信 IP 白名单只认 IP，变了必须去后台改）。

用法：
    python scripts/check_mp_ip.py            # 比对上次记录，变了就打印提示
    python scripts/check_mp_ip.py --update   # 直接把当前 IP 记为新基线

配合 automation 每天跑一次，IP 变了会输出醒目提示，避免推送时才发现 40164。
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_noise_drafts import DATA_DIR  # noqa: E402

IP_FILE = os.path.join(DATA_DIR, ".mp_ip")
SOURCES = ("https://ipv4.icanhazip.com", "https://ip.3322.net", "https://api.ipify.org")


def current_ipv4() -> str:
    for u in SOURCES:
        try:
            r = requests.get(u, timeout=8, headers={"User-Agent": "curl/8"})
            t = r.text.strip().splitlines()[0].strip()
            if t.count(".") == 3 and t.split(".")[0].isdigit():
                return t
        except Exception:
            continue
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="把当前 IP 记为基线")
    args = ap.parse_args()

    ip = current_ipv4()
    if not ip:
        print("取不到公网 IPv4，稍后重试")
        return
    prev = ""
    if os.path.exists(IP_FILE):
        prev = open(IP_FILE, encoding="utf-8").read().strip()

    if args.update or not prev:
        with open(IP_FILE, "w", encoding="utf-8") as f:
            f.write(ip)
        print(f"[基线] 已记录当前出口 IP：{ip}")
        return

    if ip == prev:
        print(f"[OK] 出口 IP 未变：{ip}")
        return

    with open(IP_FILE, "w", encoding="utf-8") as f:
        f.write(ip)
    print("=" * 56)
    print(f"出口 IP 已从 {prev} 变为 {ip}")
    print("微信 IP 白名单需要同步更新，否则推送会报 40164：")
    print("  微信开发者平台 → 我的业务 → 公众号/服务号 → 基础信息 → 开发密钥 → IP白名单")
    print("=" * 56)


if __name__ == "__main__":
    main()
