"""一条龙：popstore 数据 → 微信素材转存 → 公众号草稿箱（支持多图文一次群发）。

用法：
    python scripts/push_wechat_draft.py --latest                 # 最新已发布 → 单篇草稿
    python scripts/push_wechat_draft.py --ids id1,id2,id3        # 多图文（最多 8 篇，一次群发）
    python scripts/push_wechat_draft.py --pending --max 3        # 把未推送过的已发布店铺打包
    python scripts/push_wechat_draft.py --weekly --days 7        # 周报
    python scripts/push_wechat_draft.py --latest --dry-run       # 只生成不推
    python scripts/push_wechat_draft.py --latest --light         # 图片走 uploadimg（不占素材库配额，但不可管理）
    python scripts/push_wechat_draft.py --latest --url-link URL  # 「阅读原文」跳小程序详情页

图片管理：
    默认走 material/add_material（永久素材），文件名形如 260921_鸣潮快闪_01.jpg，
    素材库里可按日期前缀搜索/辨识（微信素材库本身没有文件夹功能，只能靠文件名分组）。
    原图同时按日期归档到 data/outbox/YYMMDD/ 便于回溯。

已推送记录写在 data/.wechat_pushed.json，避免重复推送同一家店。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_noise_drafts import _req, login, DATA_DIR  # noqa: E402
from gen_single_wechat import (  # noqa: E402
    MP_NAME, QRCODE, get_access_token, render_md, render_single, uploadimg,
)
from gen_weekly_wechat import parse_dt, pick_city_group  # noqa: E402
from gen_weekly_wechat import render_html as render_weekly_html  # noqa: E402
from gen_weekly_wechat import render_md as render_weekly_md  # noqa: E402

OUT_DIR = os.path.join(DATA_DIR, "outbox")
PUSHED_FILE = os.path.join(DATA_DIR, ".wechat_pushed.json")
MAX_ARTICLES = 8


# ── 已推送记录 ─────────────────────────────────────────────
def load_pushed() -> dict:
    if os.path.exists(PUSHED_FILE):
        try:
            return json.loads(open(PUSHED_FILE, encoding="utf-8").read())
        except Exception:
            return {}
    return {}


def save_pushed(d: dict):
    with open(PUSHED_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# ── 素材上传 ───────────────────────────────────────────────
def slug(s: str, n=10) -> str:
    s = re.sub(r'[\\/:*?"<>|\s]+', "", s or "")
    return s[:n] or "img"


def upload_permanent_image(token: str, data: bytes, filename: str) -> str:
    """永久素材（可在素材库按文件名管理），返回微信 URL"""
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image",
        files={"media": (filename, data)},
        timeout=60,
    ).json()
    if "url" not in r:
        # 配额满等情况下退化为 uploadimg
        print(f"  [降级] add_material 失败({r})，改用 uploadimg")
        r2 = requests.post(
            f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}",
            files={"media": (filename, data)},
            timeout=60,
        ).json()
        if "url" not in r2:
            raise SystemExit(f"图片上传失败: {r} / {r2}")
        return r2["url"]
    return r["url"]


def upload_thumb(token: str, data: bytes, filename="thumb.jpg") -> str:
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=thumb",
        files={"media": (filename, data)},
        timeout=60,
    ).json()
    if "media_id" not in r:
        raise SystemExit(f"封面上传失败: {r}")
    return r["media_id"]


def archive_local(date_dir: str, filename: str, data: bytes) -> str:
    d = os.path.join(OUT_DIR, date_dir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, filename)
    with open(p, "wb") as f:
        f.write(data)
    return p


def build_digest(text: str, limit=100) -> str:
    return " ".join((text or "").split())[:limit]


def store_images(store) -> list[str]:
    try:
        v = json.loads(store.get("images") or "[]")
        if isinstance(v, list) and v and isinstance(v[0], str):
            return v
    except Exception:
        pass
    return [store.get("cover_image")] if store.get("cover_image") else []


def build_article(store, wx: str, date_tag: str, light: bool, url_link: str = "", upload: bool = True):
    """单篇：转存图片 + 封面，返回草稿 article 字典"""
    title = (store.get("title") or "").strip()
    urls = store_images(store)
    wx_urls = []
    for i, u in enumerate(urls):
        fn = f"{date_tag}_{slug(title)}_{i + 1}.jpg"
        if not upload:  # dry-run：不上传、不落盘，正文保留外链
            wx_urls.append(u)
            continue
        data = requests.get(u, timeout=60).content
        archive_local(date_tag, fn, data)
        if light:
            wx_urls.append(uploadimg(wx, data, fn))
        else:
            wx_urls.append(upload_permanent_image(wx, data, fn))
        print(f"  [传图] {i + 1}/{len(urls)} {fn}")

    qrcode_src = None
    if os.path.exists(QRCODE):
        if not upload:
            qrcode_src = None
        else:
            with open(QRCODE, "rb") as f:
                qr_data = f.read()
            fn = f"{date_tag}_小程序码.png"
            archive_local(date_tag, fn, qr_data)
            qrcode_src = upload_permanent_image(wx, qr_data, fn) if not light else uploadimg(wx, qr_data, fn)
            print("  [传图] 小程序码")

    content = render_single(store, wx_urls, qrcode_src)
    md = render_md(store, wx_urls, qrcode_src)

    cover = None
    if not upload:  # dry-run：不下载封面、不上传素材（省配额，反正也不会建草稿）
        print("  [dry-run] 跳过封面上传")
        thumb_id = ""
        return {
            "title": title[:64],
            "author": MP_NAME,
            "digest": build_digest(store.get("subtitle") or store.get("description") or title),
            "content": content,
            "thumb_media_id": thumb_id,
            "content_source_url": url_link,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }, md, content

    if urls:
        cover = requests.get(urls[0], timeout=60).content
    elif os.path.exists(QRCODE):
        with open(QRCODE, "rb") as f:
            cover = f.read()
    if cover is None:
        raise SystemExit(f"{title}: 找不到可做封面的图片")
    thumb_id = upload_thumb(wx, cover, f"{date_tag}_{slug(title)}_cover.jpg")

    return {
        "title": title[:64],
        "author": MP_NAME,
        "digest": build_digest(store.get("subtitle") or store.get("description") or title),
        "content": content,
        "thumb_media_id": thumb_id,
        "content_source_url": url_link,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }, md, content


def create_draft(wx: str, articles: list[dict]) -> str:
    if len(articles) > MAX_ARTICLES:
        raise SystemExit(f"一次最多 {MAX_ARTICLES} 篇，当前 {len(articles)} 篇")
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={wx}",
        data=json.dumps({"articles": articles}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    ).json()
    if "media_id" not in r:
        raise SystemExit(f"草稿创建失败: {r}")
    return r["media_id"]


def fetch_published(token, size=100) -> list:
    d = _req("GET", f"/admin/stores?status=published&page=1&page_size={size}", token)
    return d.get("items") or d.get("results") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-id", default=None)
    ap.add_argument("--ids", default=None, help="逗号分隔，多图文一次群发（最多 8）")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--pending", action="store_true", help="未推送过的已发布店铺")
    ap.add_argument("--max", type=int, default=3, help="--pending 最多打包几篇")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--city", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--url-link", default="", help="「阅读原文」链接，可填小程序 URL Link")
    ap.add_argument("--light", action="store_true", help="图片用 uploadimg，不占素材库配额")
    ap.add_argument("--force", action="store_true", help="忽略已推送记录")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = login()
    wx = get_access_token()
    print("[公众号] access_token OK")
    date_tag = datetime.now().strftime("%y%m%d")
    pushed = load_pushed()

    articles, mds = [], []
    ids_for_record = []

    if args.weekly:
        stores = fetch_published(token)
        now = datetime.now()
        picked = []
        for s in stores:
            if args.city and (s.get("city") or "") != args.city:
                continue
            c = parse_dt(s.get("created_at"))
            if c and c >= now - timedelta(days=args.days):
                picked.append(s)
        if not picked:
            raise SystemExit("周报没有命中的店铺")
        picked.sort(key=lambda x: parse_dt(x.get("start_date")) or datetime.max)
        cities = [c for c, _ in pick_city_group(picked)]
        lead = f"本期共 {len(picked)} 场，覆盖 {'、'.join(cities[:6])}{'等' if len(cities) > 6 else ''}城市。"
        title = args.title or f"本周新增 {len(picked)} 场联名快闪｜{now.strftime('%m.%d')} 更新"
        content = render_weekly_html(picked, title, lead)
        # 周报图片：传前 12 张并替换
        raw = [(s.get("cover_image") or "") for s in picked[:12]]
        raw = [u for u in raw if u]
        for i, u in enumerate(raw):
            data = requests.get(u, timeout=60).content
            fn = f"{date_tag}_weekly_{i + 1}.jpg"
            archive_local(date_tag, fn, data)
            wx_url = uploadimg(wx, data, fn) if args.light else upload_permanent_image(wx, data, fn)
            content = content.replace(u, wx_url)
        cover = requests.get(raw[0], timeout=60).content if raw else None
        if cover is None and os.path.exists(QRCODE):
            with open(QRCODE, "rb") as f:
                cover = f.read()
        articles.append({
            "title": title[:64],
            "author": MP_NAME,
            "digest": build_digest(lead),
            "content": content,
            "thumb_media_id": upload_thumb(wx, cover, f"{date_tag}_weekly_cover.jpg"),
            "content_source_url": args.url_link,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        })
        mds.append(render_weekly_md(picked, title, lead))
    else:
        if args.ids:
            wanted = [x.strip() for x in args.ids.split(",") if x.strip()]
            id_set = set(wanted)
            stores = [s for s in fetch_published(token) if s.get("id") in id_set]
            found = {s.get("id") for s in stores}
            missing = id_set - found
            if missing:
                print(f"[警告] 这些 id 不在已发布列表里：{missing}")
        elif args.store_id:
            stores = [_req("GET", f"/admin/stores/{args.store_id}", token)]
        elif args.latest:
            stores = fetch_published(token, 1)[:1]
        elif args.pending:
            stores = [s for s in fetch_published(token) if s.get("id") not in pushed or args.force]
            stores = stores[: args.max]
            if not stores:
                print("没有未推送的店铺")
                return
        else:
            raise SystemExit("给 --store-id / --ids / --latest / --pending / --weekly")

        for s in stores:
            print(f"[目标] {s.get('title')}")
            art, md, _ = build_article(s, wx, date_tag, args.light, args.url_link,
                                       upload=not args.dry_run)
            if args.title and len(stores) == 1:
                art["title"] = args.title[:64]
            articles.append(art)
            mds.append(md)
            ids_for_record.append(s.get("id"))

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    with open(os.path.join(OUT_DIR, f"pushed-{stamp}.md"), "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(mds))
    with open(os.path.join(OUT_DIR, f"pushed-{stamp}.html"), "w", encoding="utf-8") as f:
        f.write("\n<hr/>\n".join(a["content"] for a in articles))

    print(f"\n[篇数] {len(articles)} 篇（一次群发）")
    for a in articles:
        print(f"  · {a['title']}")
    if args.dry_run:
        print("[dry-run] 已跳过推送，产物在 data/outbox/")
        return

    media_id = create_draft(wx, articles)
    print(f"\n✅ 多图文草稿已创建 media_id={media_id}")
    print("   → 公众号后台「草稿箱」核对后一次性群发")

    for sid, a in zip(ids_for_record, articles):
        pushed[sid] = {"title": a["title"], "media_id": media_id, "at": datetime.now().isoformat(timespec="seconds")}
    save_pushed(pushed)


if __name__ == "__main__":
    main()
