"""把 popstore 快闪店数据生成为公众号可用的图文（HTML + Markdown）。

用法：
    python scripts/gen_weekly_wechat.py                     # 近 7 天新增的已发布店铺
    python scripts/gen_weekly_wechat.py --days 14           # 近 14 天
    python scripts/gen_weekly_wechat.py --mode upcoming     # 即将开始（未来 30 天内 start_date）
    python scripts/gen_weekly_wechat.py --city 上海         # 只看某个城市
    python scripts/gen_weekly_wechat.py --title "本周速递"   # 自定义标题

产物写到 backend/data/outbox/：
    wechat-YYYYMMDD.html   —— 微信兼容（全内联样式，无 <style>/flex/class），供草稿箱接口或粘贴使用
    wechat-YYYYMMDD.md     —— Markdown 版，备用
控制台会列出正文里引用的外链图片（公众号正文必须换成微信素材 URL，否则发布后不显示）。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_noise_drafts import _req, login, DATA_DIR  # noqa: E402

OUT_DIR = os.path.join(DATA_DIR, "outbox")

ACCENT = "#ff5c8a"
MUTED = "#8a8a8a"

PREVIEW_TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body{{margin:0;padding:24px;background:#f2f3f5;font-family:-apple-system,"PingFang SC",sans-serif;}}
  .phone{{max-width:414px;margin:0 auto;background:#fff;border-radius:14px;box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;}}
  .bar{{background:#ededed;padding:10px 14px;font-size:13px;color:#666;}}
  .inner{{padding:16px 14px 24px;}}
  img{{max-width:100%;height:auto;}}
</style></head><body>
<div class="phone"><div class="bar">公众号预览 · {title}</div><div class="inner">
{body}
</div></div></body></html>
"""


def parse_dt(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def fmt_date(d):
    return d.strftime("%m.%d") if d else "待定"


def fmt_range(a, b):
    if not a and not b:
        return "时间待定"
    if a and b:
        same_year = a.year == b.year
        return f"{a.strftime('%Y.%m.%d') if not same_year else fmt_date(a)} - {b.strftime('%Y.%m.%d') if not same_year else fmt_date(b)}"
    return fmt_date(a or b)


def _json_list(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else [v]
    except (ValueError, TypeError):
        return [raw]


def pick_city_group(items):
    """按城市分组，保持首次出现顺序"""
    groups: dict[str, list] = {}
    order: list[str] = []
    for it in items:
        c = (it.get("city") or "其他").strip() or "其他"
        if c not in groups:
            groups[c] = []
            order.append(c)
        groups[c].append(it)
    return [(c, groups[c]) for c in order]


def cover_of(it):
    imgs = _json_list(it.get("images"))
    if imgs and isinstance(imgs[0], str):
        return imgs[0]
    return it.get("cover_image") or ""


def card_html(it):
    title = html.escape((it.get("title") or "").strip())
    sub = html.escape((it.get("subtitle") or "").strip())
    address = " · ".join(
        x for x in [it.get("district"), it.get("address")] if x
    )
    address = html.escape(address)
    period = fmt_range(parse_dt(it.get("start_date")), parse_dt(it.get("end_date")))
    tags = [t for t in _json_list(it.get("tags")) if isinstance(t, str)]
    tags = [t for t in tags if t not in ("快闪", "快闪店", "二次元")]
    tag_html = ""
    if tags:
        chips = "".join(
            f'<span style="display:inline-block;font-size:12px;color:{ACCENT};'
            f'border:1px solid {ACCENT};border-radius:10px;padding:1px 8px;margin:0 6px 4px 0;">'
            f"{html.escape(t)}</span>"
            for t in tags[:4]
        )
        tag_html = f'<p style="margin:6px 0 0;">{chips}</p>'
    sub_html = (
        f'<p style="margin:6px 0 0;font-size:14px;color:#666;line-height:1.7;">{sub}</p>'
        if sub
        else ""
    )
    img_html = ""
    cover = cover_of(it)
    if cover:
        img_html = (
            f'<img src="{html.escape(cover)}" style="width:100%;border-radius:8px;'
            f'margin:10px 0 0;display:block;" />'
        )
    org = html.escape((it.get("organizer") or "").strip())
    org_html = (
        f'<p style="margin:6px 0 0;font-size:13px;color:{MUTED};">主办：{org}</p>'
        if org
        else ""
    )
    return (
        f'<section style="border-left:4px solid {ACCENT};background:#fafafa;'
        f'padding:12px 14px;margin:14px 0;border-radius:6px;">'
        f'<p style="margin:0;font-size:16px;font-weight:bold;line-height:1.5;color:#222;">{title}</p>'
        f'{sub_html}'
        f'<p style="margin:8px 0 0;font-size:14px;color:#555;">日期：{period}</p>'
        + (f'<p style="margin:4px 0 0;font-size:14px;color:#555;">地点：{address}</p>' if address else "")
        + org_html
        + tag_html
        + img_html
        + "</section>"
    )


def render_html(items, title, lead):
    body = []
    if lead:
        body.append(
            f'<p style="margin:0 0 16px;font-size:15px;color:#555;line-height:1.8;">'
            f"{html.escape(lead)}</p>"
        )
    for city, group in pick_city_group(items):
        body.append(
            f'<h2 style="font-size:17px;font-weight:bold;color:#222;margin:22px 0 4px;'
            f'padding-left:10px;border-left:4px solid {ACCENT};">'
            f"{html.escape(city)} · {len(group)} 场</h2>"
        )
        for it in group:
            body.append(card_html(it))
    foot = (
        '<section style="margin-top:26px;padding-top:14px;border-top:1px dashed #ddd;">'
        f'<p style="font-size:13px;color:{MUTED};line-height:1.8;margin:0;">'
        "以上信息整理自公开渠道，具体以主办方现场公告为准。<br/>"
        "想随时查附近正在进行的快闪，可以打开「快闪地图」小程序看看。</p></section>"
    )
    body.append(foot)
    inner = "\n".join(body)
    return (
        f'<section style="font-size:15px;color:#333;line-height:1.75;padding:2px 4px;">\n'
        f"{inner}\n</section>"
    )


def render_md(items, title, lead):
    lines = [f"# {title}", ""]
    if lead:
        lines += [lead, ""]
    for city, group in pick_city_group(items):
        lines.append(f"## {city} · {len(group)} 场")
        lines.append("")
        for it in group:
            period = fmt_range(parse_dt(it.get("start_date")), parse_dt(it.get("end_date")))
            addr = " · ".join(x for x in [it.get("district"), it.get("address")] if x)
            lines.append(f"**{it.get('title')}**")
            lines.append(f"- 日期：{period}")
            if addr:
                lines.append(f"- 地点：{addr}")
            if it.get("organizer"):
                lines.append(f"- 主办：{it.get('organizer')}")
            tags = [t for t in _json_list(it.get("tags")) if isinstance(t, str)]
            if tags:
                lines.append(f"- 标签：{' / '.join(tags)}")
            cover = cover_of(it)
            if cover:
                lines.append(f"![]({cover})")
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="回看天数（new 模式）/ 未来天数（upcoming 模式）")
    ap.add_argument("--mode", choices=("new", "upcoming"), default="new")
    ap.add_argument("--city", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--status", default="published")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    token = login()
    data = _req("GET", f"/admin/stores?status={args.status}&page=1&page_size={args.limit}", token)
    stores = data.get("items") or data.get("results") or []
    print(f"[接口] status={args.status} 取回 {len(stores)} 条")

    now = datetime.now()
    picked = []
    for s in stores:
        if args.city and (s.get("city") or "") != args.city:
            continue
        if args.mode == "new":
            c = parse_dt(s.get("created_at"))
            if c and c >= now - timedelta(days=args.days):
                picked.append(s)
        else:
            st = parse_dt(s.get("start_date"))
            if st and now <= st <= now + timedelta(days=args.days):
                picked.append(s)

    picked.sort(key=lambda x: parse_dt(x.get("start_date")) or datetime.max)
    print(f"[筛选] mode={args.mode} days={args.days} → 命中 {len(picked)} 条")
    if not picked:
        print("没有符合条件的店铺，换个 --days 或 --mode 试试")
        return

    if args.title:
        title = args.title
    elif args.mode == "new":
        title = f"本周新增 {len(picked)} 场二次元快闪｜{now.strftime('%m.%d')} 更新"
    else:
        title = f"接下来 {args.days} 天有 {len(picked)} 场快闪开跑｜{now.strftime('%m.%d')} 更新"

    cities = [c for c, _ in pick_city_group(picked)]
    lead = f"本期共 {len(picked)} 场，覆盖 {'、'.join(cities[:6])}{'等' if len(cities) > 6 else ''}城市。"

    html_body = render_html(picked, title, lead)
    md_body = render_md(picked, title, lead)

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = now.strftime("%Y%m%d")
    html_path = os.path.join(OUT_DIR, f"wechat-{stamp}.html")
    md_path = os.path.join(OUT_DIR, f"wechat-{stamp}.md")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_body)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_body)

    # 手机宽度预览外壳（仅本地看效果用，不要推公众号）
    preview_path = os.path.join(OUT_DIR, f"wechat-{stamp}-preview.html")
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(PREVIEW_TPL.format(title=html.escape(title), body=html_body))

    images = [cover_of(i) for i in picked]
    images = [i for i in images if i]
    print(f"\n[标题] {title}")
    print(f"[产出] HTML: {html_path}")
    print(f"[产出] Markdown: {md_path}")
    print(f"\n[图片] 正文引用 {len(images)} 张外链图，推公众号前需转存微信素材：")
    for u in images[:5]:
        print("   ", u)
    if len(images) > 5:
        print(f"    … 共 {len(images)} 张")


if __name__ == "__main__":
    main()
