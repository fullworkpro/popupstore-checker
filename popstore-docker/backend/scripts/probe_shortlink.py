"""探测当前小程序是否具备生成 Short Link（`wxa/genwxashortlink`）的权限。

背景：官方文档注明 generateShortLink「目前对所有非个人主体小程序开放」，
个人主体大概率返回 43104（this appid does not have permission）。
本脚本用于实测：拿小程序 access_token → 分别请求首页与详情页 Short Link，
把 errcode / errmsg / link 原样打印，便于判断能否程序化生成「可点击跳小程序」的链接。

用法：
    python scripts/probe_shortlink.py                       # 试首页 + 一个示例详情页
    python scripts/probe_shortlink.py --page "pages/detail/detail?id=xxxx" --title "某快闪"
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_single_wechat import get_miniapp_token  # noqa: E402

API = "https://api.weixin.qq.com/wxa/genwxashortlink"


def gen(token: str, page_url: str, title: str, permanent: bool):
    body = {"page_url": page_url, "page_title": title[:20], "is_permanent": permanent}
    try:
        r = requests.post(f"{API}?access_token={token}", json=body, timeout=30).json()
    except Exception as e:  # noqa: BLE001
        return {"errcode": -1, "errmsg": f"请求异常 {e}"}
    return r


def hint(code):
    return {
        0: "✅ 可用：返回 link 即可直接放进公众号正文（微信内可点开小程序）",
        43104: "❌ 无调用权限：个人主体 / 非开放类目（文档：仅非个人主体，且 43104 说明仅电商类目）",
        40066: "❌ 页面不存在：page_url 必须是已发布小程序里真实存在的页面（含 query 也要真实）",
        40225: "❌ 页面标题非法",
        85400: "❌ 永久 Short Link 已达 10 万上限",
        45009: "❌ 当日生成量超上限",
        40001: "❌ access_token 无效（AppSecret 错 / 不是该 appid 的 token）",
    }.get(code, "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="", help="额外试一个页面路径，如 pages/detail/detail?id=xxx")
    ap.add_argument("--title", default="快闪详情")
    ap.add_argument("--permanent", action="store_true", help="试永久有效（占 10 万配额，慎用）")
    args = ap.parse_args()

    token = get_miniapp_token()
    if not token:
        print("❌ 拿不到小程序 access_token：检查 backend/data/.wechat_mp 的 WXAPP_APPID / WXAPP_APPSECRET")
        return

    cases = [("pages/index/index", "快闪首页")]
    if args.page:
        cases.append((args.page, args.title))

    for url, title in cases:
        r = gen(token, url, title, args.permanent)
        code = r.get("errcode")
        print(f"\n[请求] page_url={url}  is_permanent={args.permanent}")
        print(f"[返回] {json.dumps(r, ensure_ascii=False)}")
        print(f"[解读] {hint(code)}")
        if code == 0:
            print(f"[链接] {r.get('link')}")


if __name__ == "__main__":
    main()
