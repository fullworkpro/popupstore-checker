"""探测公众号 draft/add 是否接受自定义 `<mp-miniprogram>` 小程序卡片标签。

背景：v1.4.18 在正文插入小程序卡片后，建草稿报 `45166 invalid content`。
本脚本用同一张封面，对几种标签写法各建一篇草稿（标题带 [探测] 前缀），
把 errcode 原样打印：0 = 该写法可用，去草稿箱确认是否渲染成卡片即可。
失败的草稿不会创建；成功的草稿请在公众号后台手工删除。

用法：
    python scripts/probe_minicard.py            # 试全部写法
    python scripts/probe_minicard.py --only A   # 只试某一种
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_single_wechat import get_access_token, read_credential_dict  # noqa: E402
from push_wechat_draft import upload_thumb  # noqa: E402


def build_cases(appid: str, nickname: str):
    path = "pages/detail/detail?id=probe"
    return {
        "A_完整属性": (
            f'<mp-miniprogram data-miniprogram-appid="{appid}" data-miniprogram-path="{path}" '
            f'data-miniprogram-nickname="{nickname}" data-miniprogram-title="查看本店详情" '
            f'data-miniprogram-type="card" data-miniprogram-servicetype="0"></mp-miniprogram>'
        ),
        "B_最小属性": (
            f'<mp-miniprogram data-miniprogram-appid="{appid}" data-miniprogram-path="{path}">'
            f"</mp-miniprogram>"
        ),
        "C_带avatar": (
            f'<mp-miniprogram data-miniprogram-appid="{appid}" data-miniprogram-path="{path}" '
            f'data-miniprogram-nickname="{nickname}" data-miniprogram-title="查看本店详情" '
            f'data-miniprogram-avatar="https://mmbiz.qpic.cn/mmbiz_png/0/0" '
            f'data-miniprogram-type="card"></mp-miniprogram>'
        ),
    }


def add_draft(token: str, title: str, content: str, thumb: str) -> dict:
    body = {
        "articles": [{
            "title": title[:64],
            "author": "probe",
            "digest": "小程序卡片探测，可删",
            "content": content,
            "thumb_media_id": thumb,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }]
    }
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    ).json()
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只试某个用例，如 A_完整属性")
    args = ap.parse_args()

    cred = read_credential_dict()
    appid = cred.get("WXAPP_APPID", "")
    if not appid:
        print("❌ 缺少 WXAPP_APPID：检查 backend/data/.wechat_mp")
        return

    token = get_access_token()
    if not token:
        print("❌ 拿不到公众号 access_token（检查凭据 / IP 白名单 40164）")
        return

    # 封面：复用本地通用码图片，只占 1 个素材位
    from gen_single_wechat import QRCODE
    if not os.path.exists(QRCODE):
        print(f"❌ 找不到封面图 {QRCODE}")
        return
    with open(QRCODE, "rb") as f:
        thumb = upload_thumb(token, f.read(), "probe_thumb.png")
    print(f"封面 media_id = {thumb}")

    cases = build_cases(appid, "wing的附近溜达本")
    for name, tag in cases.items():
        if args.only and args.only not in name:
            continue
        title = f"[探测] 小程序卡片 {name}"
        r = add_draft(token, title, f"<p>{name}</p>{tag}", thumb)
        code = r.get("errcode")
        flag = "✅ 可接受" if code == 0 else "❌ 被拒绝"
        print(f"{flag} {name}: {json.dumps(r, ensure_ascii=False)}")

    print("\n说明：只有 errcode=0 的草稿会真的进草稿箱，请去公众号后台确认是否渲染成卡片后删除。")


if __name__ == "__main__":
    main()
