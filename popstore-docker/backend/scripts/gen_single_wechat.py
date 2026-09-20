"""单篇快闪推文生成器：文字信息卡在前 → 图片平铺 → 小程序码引流收尾。

用法：
    python scripts/gen_single_wechat.py <store_id>          # 指定店铺
    python scripts/gen_single_wechat.py --latest            # 最新一条已发布
    python scripts/gen_single_wechat.py --latest --upload   # 同时把外链图转存为微信素材 URL

图片转存说明：公众号正文只认 mmbiz.qpic.cn 素材 URL，外链图（NAS 图床）发布后会裂。
--upload 需要公众号凭据：backend/data/.wechat_mp（WECHAT_APPID=... / WECHAT_APPSECRET=...），
且调用机器的出口 IP 已加入公众号后台 IP 白名单。个人未认证号若无权限，会返回 48001。

产物写到 backend/data/outbox/：wechat-single-<id前8>.html / .md / -preview.html
"""
from __future__ import annotations

import argparse
import html
import io
import json
import os
import sys
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_noise_drafts import _req, login, DATA_DIR  # noqa: E402
from gen_weekly_wechat import (  # noqa: E402
    OUT_DIR, PREVIEW_TPL, _json_list, fmt_range, parse_dt,
)

ACCENT = "#ff5c8a"
MUTED = "#8a8a8a"
ASSETS = os.path.join(DATA_DIR, "assets")
QRCODE = os.path.join(ASSETS, "xcx-qrcode.png")
CRED = os.path.join(DATA_DIR, ".wechat_mp")
MP_NAME = os.environ.get("MP_NAME", "wing的附近溜达本")
MP_SLOGAN = os.environ.get("MP_SLOGAN", "附近的联名快闪 / 特展 / 联名餐厅，随手一查")
UPLOAD_LIMIT_MB = 10


def read_credentials():
    if not os.path.exists(CRED):
        return None
    d = {}
    with open(CRED, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    if d.get("WECHAT_APPID") and d.get("WECHAT_APPSECRET"):
        return d["WECHAT_APPID"], d["WECHAT_APPSECRET"]
    return None


def get_access_token():
    cred = read_credentials()
    if not cred:
        raise SystemExit(f"缺少凭据文件 {CRED}（WECHAT_APPID=... / WECHAT_APPSECRET=...）")
    r = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={"grant_type": "client_credential", "appid": cred[0], "secret": cred[1]},
        timeout=15,
    ).json()
    if "access_token" not in r:
        code = r.get("errcode")
        hint = {"48001": "该公众号没有接口权限（个人未认证号典型表现）→ 走 HTML 复制粘贴通道",
                "40164": "出口 IP 不在白名单 → 公众号后台把本机公网 IP 加进「IP白名单」",
                "40013": "AppID 无效"}.get(code, "")
        raise SystemExit(f"获取 access_token 失败: {r} {hint}")
    return r["access_token"]


def uploadimg(token: str, data: bytes, filename: str) -> str:
    if len(data) > UPLOAD_LIMIT_MB * 1024 * 1024:
        raise SystemExit(f"图片 {filename} 超过 {UPLOAD_LIMIT_MB}MB，先压缩再传")
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}",
        files={"media": (filename, data)},
        timeout=60,
    ).json()
    if "url" not in r:
        raise SystemExit(f"uploadimg 失败: {r}")
    return r["url"]


def collect_images(store, token=None):
    """返回 [(url, bytes|None)]：upload 模式下把外链换成微信 URL"""
    urls = [u for u in _json_list(store.get("images")) if isinstance(u, str) and u]
    if not urls and store.get("cover_image"):
        urls = [store["cover_image"]]
    out = []
    for i, u in enumerate(urls):
        if token:
            data = requests.get(u, timeout=60).content
            wx_url = uploadimg(token, data, f"cover{i}.jpg")
            print(f"  [传图] {i + 1}/{len(urls)} -> {wx_url[:72]}…")
            out.append(wx_url)
        else:
            out.append(u)
    return out


def info_section(store, qrcode_src=None):
    """文字信息卡（正文开头）"""
    sub = html.escape((store.get("subtitle") or "").strip())
    tags = [t for t in _json_list(store.get("tags")) if isinstance(t, str)]
    tags = [t for t in tags if t not in ("快闪", "快闪店", "二次元")]
    period = fmt_range(parse_dt(store.get("start_date")), parse_dt(store.get("end_date")))
    addr = " · ".join(x for x in [store.get("district"), store.get("address")] if x)
    rows = [("日期", period)]
    if addr:
        rows.append(("地点", html.escape(addr)))
    if store.get("organizer"):
        rows.append(("主办", html.escape(store["organizer"])))
    if store.get("reservation") == "yes":
        rows.append(("入场", "需预约，请留意主办方公告"))
    rows_html = "".join(
        f'<p style="margin:6px 0;font-size:14px;color:#555;">'
        f'<strong style="color:{MUTED};font-weight:normal;display:inline-block;width:38px;">{k}</strong>{v}</p>'
        for k, v in rows
    )
    chips = "".join(
        f'<span style="display:inline-block;font-size:12px;color:{ACCENT};border:1px solid {ACCENT};'
        f'border-radius:10px;padding:1px 8px;margin:0 6px 4px 0;">{html.escape(t)}</span>'
        for t in tags[:4]
    )
    desc = (store.get("description") or "").strip()
    desc_html = (
        "".join(
            f'<p style="margin:0 0 12px;font-size:15px;color:#333;line-height:1.85;">{html.escape(p.strip())}</p>'
            for p in desc.splitlines() if p.strip()
        )
        if desc
        else ""
    )
    tip = (
        f'<p style="margin:2px 0 0;font-size:13px;color:{MUTED};">活动信息整理自公开渠道，具体以主办方现场公告为准。</p>'
    )
    src = (store.get("source_url") or "").strip()
    src_html = (
        f'<p style="margin:6px 0 0;font-size:13px;color:{MUTED};">原文：{html.escape(src)}</p>' if src else ""
    )
    return (
        f'<section style="border-left:4px solid {ACCENT};background:#fafafa;padding:14px 16px;'
        f'margin:0 0 18px;border-radius:6px;">'
        f'<h2 style="margin:0 0 4px;font-size:18px;line-height:1.5;color:#222;">'
        f'{html.escape((store.get("title") or "").strip())}</h2>'
        + (f'<p style="margin:0 0 8px;font-size:14px;color:#888;">{sub}</p>' if sub else "")
        + rows_html
        + (f'<p style="margin:8px 0 0;">{chips}</p>' if chips else "")
        + f"</section>"
        + desc_html
        + src_html
        + tip
    )


def gallery_section(image_urls):
    if not image_urls:
        return ""
    parts = ['<section style="margin:0 0 6px;">']
    for u in image_urls:
        parts.append(
            f'<img src="{html.escape(u)}" style="width:100%;display:block;border-radius:8px;margin:0 0 12px;" />'
        )
    parts.append("</section>")
    return "".join(parts)


def cta_section(qrcode_src):
    qr = (
        f'<img src="{html.escape(qrcode_src)}" style="width:180px;height:180px;display:block;margin:0 auto;" />'
        if qrcode_src
        else ""
    )
    return (
        f'<section style="margin:26px 0 0;padding:20px 16px 22px;background:#fff5f8;'
        f'border-radius:10px;text-align:center;">'
        f'<p style="margin:0 0 12px;font-size:15px;font-weight:bold;color:{ACCENT};">'
        f"随时随地查快闪 · 就在「{MP_NAME}」小程序</p>"
        f"{qr}"
        f'<p style="margin:12px 0 0;font-size:13px;color:{MUTED};line-height:1.8;">'
        f"长按识别小程序码<br/>{html.escape(MP_SLOGAN)}</p></section>"
    )


def render_single(store, image_urls, qrcode_src=None):
    body = (
        info_section(store)
        + gallery_section(image_urls)
        + cta_section(qrcode_src)
    )
    return (
        '<section style="font-size:15px;color:#333;line-height:1.75;padding:2px 4px;">\n'
        f"{body}\n</section>"
    )


def render_md(store, image_urls, qrcode_src=None):
    period = fmt_range(parse_dt(store.get("start_date")), parse_dt(store.get("end_date")))
    addr = " · ".join(x for x in [store.get("district"), store.get("address")] if x)
    lines = [f"# {store.get('title')}", ""]
    if store.get("subtitle"):
        lines += [store["subtitle"], ""]
    lines += [f"- 日期：{period}"]
    if addr:
        lines.append(f"- 地点：{addr}")
    if store.get("organizer"):
        lines.append(f"- 主办：{store['organizer']}")
    lines.append("")
    if store.get("description"):
        lines += [store["description"], ""]
    for u in image_urls:
        lines += [f"![]({u})", ""]
    lines += [f"> 长按识别小程序码，{MP_SLOGAN} ——「{MP_NAME}」", ""]
    if qrcode_src:
        lines += [f"![]({qrcode_src})", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store_id", nargs="?", default=None)
    ap.add_argument("--latest", action="store_true", help="取最新一条已发布")
    ap.add_argument("--upload", action="store_true", help="把外链图转存为微信素材 URL")
    ap.add_argument("--status", default="published")
    args = ap.parse_args()

    token = login()
    if args.latest:
        d = _req("GET", f"/admin/stores?status={args.status}&page=1&page_size=1", token)
        stores = d.get("items") or []
        if not stores:
            raise SystemExit("没有已发布店铺")
        store = stores[0]
    elif args.store_id:
        store = _req("GET", f"/admin/stores/{args.store_id}", token)
    else:
        raise SystemExit("给 store_id 或 --latest")

    print(f"[目标] {store.get('title')}（{store.get('id')}）")

    wx_token = get_access_token() if args.upload else None
    if args.upload:
        print("[转存] 开始把外链图上传为微信素材…")

    image_urls = collect_images(store, wx_token)

    qrcode_src = None
    if os.path.exists(QRCODE):
        if wx_token:
            with open(QRCODE, "rb") as f:
                qrcode_src = uploadimg(wx_token, f.read(), "xcx-qrcode.png")
                print(f"  [传图] 小程序码 -> {qrcode_src[:72]}…")
        else:
            qrcode_src = "data:image/png;base64,__LOCAL_QRCODE__"  # 本地预览占位
    else:
        print(f"[警告] 找不到小程序码 {QRCODE}，收尾区将没有二维码")

    html_body = render_single(store, image_urls, qrcode_src)
    md_body = render_md(store, image_urls, qrcode_src)

    os.makedirs(OUT_DIR, exist_ok=True)
    sid = store.get("id", "")[:8] or datetime.now().strftime("%H%M%S")
    html_path = os.path.join(OUT_DIR, f"wechat-single-{sid}.html")
    md_path = os.path.join(OUT_DIR, f"wechat-single-{sid}.md")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_body)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_body)

    # 本地预览：把占位换成本地文件 base64
    preview_body = html_body
    if os.path.exists(QRCODE):
        import base64

        with open(QRCODE, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        preview_body = preview_body.replace("data:image/png;base64,__LOCAL_QRCODE__", f"data:image/png;base64,{b64}")
    preview_path = os.path.join(OUT_DIR, f"wechat-single-{sid}-preview.html")
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(PREVIEW_TPL.format(title=html.escape(store.get("title") or "单篇预览"), body=preview_body))

    print(f"\n[产出] HTML: {html_path}")
    print(f"[产出] Markdown: {md_path}")
    print(f"[产出] 预览: {preview_path}")
    if not args.upload:
        print("\n[提示] 本次未转存图片（--upload 未开）。正文里仍是 NAS 外链图，")
        print("       推公众号前务必 --upload 转存，否则发布后图片不显示。")


if __name__ == "__main__":
    main()
