"""探测公众号 draft/add 是否接受「小程序文字链接」<a class="weapp_text_link">。

背景：v1.4.22 想把文首引流改成微信编辑器同款的小程序文字链接
（编辑器「插入小程序 → 文字」产出的就是带 data-miniprogram-* 的 <a> 标签）。
此前 <mp-miniprogram> 卡片被拒（45166 invalid content），所以文字链接也必须先实测。

注意：draft/add **成功时不返回 errcode 字段**，只有 media_id，所以判定必须
`r.get("errcode", 0) == 0`。建草稿后会再用 draft/get 回查正文，确认
data-miniprogram-* 属性没被微信清洗掉（没被洗掉才真的可点）。

用法：
    python scripts/probe_weapplink.py            # 试全部写法
    python scripts/probe_weapplink.py --only B   # 只试某一种
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_single_wechat import QRCODE, get_access_token, read_credential_dict  # noqa: E402
from push_wechat_draft import upload_thumb  # noqa: E402

NICKNAME = "wing的附近溜达本"


def build_cases(appid: str):
    path = "pages/index/index"
    base = (
        f'<a class="weapp_text_link js_weapp_entry wx_tap_link js_wx_tap_highlight" '
        f'data-miniprogram-type="text" data-miniprogram-appid="{appid}" '
        f'data-miniprogram-path="{path}" data-miniprogram-nickname="{NICKNAME}" '
        f'data-miniprogram-servicetype="0" data-miniprogram-applink="" href="">{NICKNAME}</a>'
    )
    return {
        "A_编辑器原样": (
            '<p style="margin:0;font-size:14px;line-height:1.75;color:#5b4bd6;">'
            '<span>更多快闪内容可见小程序☞「'
            f'<a class="weapp_text_link js_weapp_entry wx_tap_link js_wx_tap_highlight" '
            f'data-unique-id="probe0000-000000" data-miniprogram-type="text" '
            f'data-miniprogram-appid="{appid}" data-miniprogram-path="{path}" '
            f'data-miniprogram-nickname="{NICKNAME}" data-miniprogram-servicetype="0" '
            f'data-miniprogram-applink="" href="" link-id="probe001">{NICKNAME}</a>'
            '」</span></p>'
        ),
        "B_精简无随机ID": (
            f'<p style="margin:0;font-size:14px;line-height:1.75;color:#5b4bd6;">'
            f"更多快闪内容可见小程序☞「{base}」</p>"
        ),
        "C_裸a无class": (
            f'<p style="margin:0;font-size:14px;line-height:1.75;color:#5b4bd6;">'
            f"更多快闪内容可见小程序☞「"
            f'<a data-miniprogram-appid="{appid}" data-miniprogram-path="{path}" '
            f'data-miniprogram-nickname="{NICKNAME}" data-miniprogram-type="text" '
            f'data-miniprogram-servicetype="0" href="">{NICKNAME}</a>」</p>'
        ),
        "D_详情页path": (
            f'<p style="margin:0;font-size:14px;line-height:1.75;color:#5b4bd6;">'
            f'<a class="weapp_text_link" data-miniprogram-type="text" '
            f'data-miniprogram-appid="{appid}" '
            f'data-miniprogram-path="pages/detail/detail?id=probe123456" '
            f'data-miniprogram-nickname="{NICKNAME}" data-miniprogram-servicetype="0" '
            f'data-miniprogram-applink="" href="">查看本店详情</a></p>'
        ),
    }


def fetch_back(token: str, media_id: str) -> str:
    """回查草稿正文，确认 data-miniprogram-* 属性是否被微信保留。"""
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/get?access_token={token}",
        data=json.dumps({"media_id": media_id}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    ).json()
    if r.get("errcode"):
        return f"回查失败 {json.dumps(r, ensure_ascii=False)}"
    return (r.get("news_item") or [{}])[0].get("content", "") or ""


def add_draft(token: str, title: str, content: str, thumb: str) -> dict:
    body = {
        "articles": [{
            "title": title[:64],
            "author": "probe",
            "digest": "小程序文字链接探测，可删",
            "content": content,
            "thumb_media_id": thumb,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }]
    }
    return requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    ).json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只试某个用例关键字，如 B 或 D")
    args = ap.parse_args()

    cred = read_credential_dict()
    appid = cred.get("WXAPP_APPID", "")
    if not appid:
        print("缺少 WXAPP_APPID：检查 backend/data/.wechat_mp")
        return

    token = get_access_token()
    if not token:
        print("拿不到公众号 access_token（检查凭据 / IP 白名单 40164）")
        return

    if not os.path.exists(QRCODE):
        print(f"找不到封面图 {QRCODE}")
        return
    with open(QRCODE, "rb") as f:
        thumb = upload_thumb(token, f.read(), "probe_thumb.png")
    print(f"封面 media_id = {thumb}")

    keep = {}
    for name, frag in build_cases(appid).items():
        if args.only and args.only not in name:
            continue
        r = add_draft(token, f"[探测] 小程序文字链接 {name}", f"<p>{name}</p>{frag}", thumb)
        code = r.get("errcode", 0)
        ok = code == 0
        print(f"{'OK 可接受' if ok else 'X  被拒绝'} {name}: {json.dumps(r, ensure_ascii=False)}")
        if not ok or not r.get("media_id"):
            continue
        keep[name] = r["media_id"]
        body = fetch_back(token, r["media_id"])
        kept = ("weapp_text_link" in body or "data-miniprogram-appid" in body)
        path_kept = "data-miniprogram-path" in body
        print(f"    回查：链接class/appid保留={kept}｜path保留={path_kept}")

    print("\n建成功的 media_id：")
    for k, v in keep.items():
        print(f"  {k}: {v}")

    print("\n说明：只有 errcode=0 的草稿会进草稿箱，确认渲染效果后请手工删除。")


if __name__ == "__main__":
    main()
