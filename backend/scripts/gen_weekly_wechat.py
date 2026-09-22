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
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clean_noise_drafts import _req, login, DATA_DIR  # noqa: E402

OUT_DIR = os.path.join(DATA_DIR, "outbox")

# 配色与小程序保持一致（小程序主色 #6C5CE7）
ACCENT = "#6C5CE7"        # 主紫：标题、标签、强调
ACCENT_DEEP = "#5b4bd6"   # 深紫：分组小标题
ACCENT_SOFT = "#f4f0ff"   # 浅紫底：信息卡 / 引流区
ACCENT_LINE = "#d9c8ff"   # 浅紫描边
MUTED = "#8a8a8a"         # 次要文字

CRED = os.path.join(DATA_DIR, ".wechat_mp")


def _read_cred() -> dict:
    d = {}
    if os.path.exists(CRED):
        with open(CRED, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
    return d


_CRED = _read_cred()

MP_NAME = os.environ.get("MP_NAME", "wing的附近溜达本")
MP_SLOGAN = os.environ.get("MP_SLOGAN", "附近的联名快闪 / 特展 / 联名餐厅，随手一查")
# 小程序首页链接：手机上打开小程序首页 → 右上角「…」→ 复制页面链接，形如 #小程序://名称/短码
# 优先级：环境变量 > 凭据文件 .wechat_mp 的 MP_HOME_LINK > 默认值
# 注意：Short Link 服务端接口（wxa/genwxashortlink）个人主体无权限（实测 43104），
#       无法程序化生成，只能这样手工取一次；留空则不加文首引流条。
MP_HOME_LINK = (
    os.environ.get("MP_HOME_LINK")
    or _CRED.get("MP_HOME_LINK")
    or "#小程序://wing的附近溜达本/vtREo1iRntOg2Kt"
)

# 小程序卡片（正文内原生 <mp-miniprogram>）：可点直达任意页面，不依赖 Short Link 接口
WXAPP_APPID = os.environ.get("WXAPP_APPID") or _CRED.get("WXAPP_APPID", "")
# 默认关闭：v1.4.18 实测微信 draft/add 会拒绝自定义 <mp-miniprogram>（45166 invalid content），
# 开启前请先用 scripts/probe_minicard.py 验证当前号是否接受该标签。
MP_MINI_CARD = (os.environ.get("MP_MINI_CARD") or _CRED.get("MP_MINI_CARD", "0")) not in (
    "0", "false", "False", "no",
)
MINI_HOME_PATH = os.environ.get("MINI_HOME_PATH", "pages/index/index")

# 小程序「文字链接」：微信编辑器插入小程序的原生产物（<a class="weapp_text_link">），
# 点击直达 data-miniprogram-path 指定页面。v1.4.22 起作为文首引流的首选形态：
# 只要 data-* 属性齐全，微信端会把它渲染成可点的蓝色小程序文字链接。
# 设为 0 可回退到旧的 #小程序:// 纯文本（.wechat_mp 里写 MP_WEAPP_LINK=0）。
MP_WEAPP_LINK = (os.environ.get("MP_WEAPP_LINK") or _CRED.get("MP_WEAPP_LINK", "1")) not in (
    "0", "false", "False", "no",
)


def weapp_text_link_html(path: str, text: Optional[str] = None) -> str:
    """生成微信小程序文字链接（等价于编辑器里「插入小程序 → 文字」）。

    - path：小程序页面路径，如 pages/index/index、pages/detail/detail?id=xxx
    - text：链接文字，默认用小程序名
    - 缺少 WXAPP_APPID 或开关关闭时返回空串，调用方需自行兜底
    """
    if not MP_WEAPP_LINK or not WXAPP_APPID or not path:
        return ""
    return (
        f'<a class="weapp_text_link js_weapp_entry wx_tap_link js_wx_tap_highlight" '
        f'data-miniprogram-type="text" '
        f'data-miniprogram-appid="{html.escape(WXAPP_APPID)}" '
        f'data-miniprogram-path="{html.escape(path)}" '
        f'data-miniprogram-nickname="{html.escape(MP_NAME)}" '
        f'data-miniprogram-servicetype="0" data-miniprogram-applink="" href="">'
        f"{html.escape(text or MP_NAME)}</a>"
    )


def mini_card_html(path: str, title: str):
    """正文内小程序卡片：点击直达 path 指定页面（首页 / 店铺详情页均可）。

    个人主体调不了 Short Link API，改用公众号正文原生 <mp-miniprogram> 标签；
    若微信端未渲染成卡片，可在 .wechat_mp 里设 MP_MINI_CARD=0 关闭。
    """
    if not MP_MINI_CARD or not WXAPP_APPID or not path:
        return ""
    return (
        f'<mp-miniprogram data-miniprogram-appid="{html.escape(WXAPP_APPID)}" '
        f'data-miniprogram-path="{html.escape(path)}" '
        f'data-miniprogram-nickname="{html.escape(MP_NAME)}" '
        f'data-miniprogram-title="{html.escape(title)}" '
        f'data-miniprogram-type="card" data-miniprogram-servicetype="0"></mp-miniprogram>'
    )

PREVIEW_TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body{{margin:0;padding:24px;background:#f3f1fa;font-family:-apple-system,"PingFang SC",sans-serif;}}
  .phone{{max-width:414px;margin:0 auto;background:#fff;border-radius:14px;box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;}}
  .bar{{background:#ece7fb;padding:10px 14px;font-size:13px;color:#5b4bd6;}}
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


def venue_lines(store):
    """「城市 + 地址」列表（不含 xx 区）；多城市店铺逐条列出

    cities 是 JSON 数组 [{"city","district","address"}, ...]；
    老数据没有 cities 时回退用主 city + address。
    """
    out, seen = [], set()

    def _join(city, addr, district=""):
        city, addr = (city or "").strip(), (addr or "").strip()
        district = (district or "").strip()
        # 推文只要「城市 + 地址」，不显示 xx 区：地址里若夹带了区名就去掉
        if district and district in addr:
            addr = addr.replace(district, "").strip(" ··")
        if city and addr:
            # 地址本身已以城市开头（如「广州时尚天河…」）时不再重复城市名
            return addr if addr.startswith(city) else f"{city} · {addr}"
        return city or addr

    for c in _json_list(store.get("cities")):
        if not isinstance(c, dict):
            continue
        line = _join(c.get("city"), c.get("address"), c.get("district"))
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    if not out:
        line = _join(store.get("city"), store.get("address"), store.get("district"))
        if line:
            out.append(line)
    return out


def address_block_html(label, addrs, color="#555"):
    """单地点一行；多地点「地点：」后逐条列出"""
    if not addrs:
        return ""
    esc = [html.escape(a) for a in addrs]
    if len(esc) == 1:
        return (f'<p style="margin:4px 0 0;font-size:14px;color:{color};">'
                f'{label}{esc[0]}</p>')
    rows = "".join(
        f'<p style="margin:2px 0 2px 8px;font-size:14px;color:{color};">{a}</p>'
        for a in esc
    )
    return (f'<p style="margin:4px 0 0;font-size:14px;color:{color};">{label}</p>{rows}')


def home_link_html():
    """文首引流条（浅紫底 + 紫色左边框）：小程序名即为可点文字链接，直达小程序首页。

    优先用微信编辑器同款的 <a class="weapp_text_link">（v1.4.22），
    未配置小程序 appid 时退回 #小程序:// 纯文本。
    """
    link = weapp_text_link_html(MINI_HOME_PATH)
    if link:
        text = (
            f'<p style="margin:0;font-size:14px;line-height:1.75;color:{ACCENT_DEEP};">'
            f"更多快闪内容可见小程序☞「{link}」</p>"
        )
    elif MP_HOME_LINK:
        text = (
            f'<p style="margin:0;font-size:14px;line-height:1.75;color:{ACCENT_DEEP};">'
            f"更多快闪内容可见小程序「{html.escape(MP_NAME)}」→ {html.escape(MP_HOME_LINK)}"
            f"</p>"
        )
    else:
        return ""
    return (
        f'<section style="margin:0 0 16px;padding:10px 12px;background:{ACCENT_SOFT};'
        f'border-left:3px solid {ACCENT};border-radius:6px;">'
        f"{text}"
        f"{mini_card_html(MINI_HOME_PATH, f'{MP_NAME} · 首页')}"
        f"</section>"
    )


def card_html(it):
    title = html.escape((it.get("title") or "").strip())
    sub = html.escape((it.get("subtitle") or "").strip())
    period = fmt_range(parse_dt(it.get("start_date")), parse_dt(it.get("end_date")))
    addrs = venue_lines(it)
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
        f'<section style="border-left:4px solid {ACCENT};background:{ACCENT_SOFT};'
        f'padding:12px 14px;margin:14px 0;border-radius:6px;">'
        f'<p style="margin:0;font-size:16px;font-weight:bold;line-height:1.5;color:#222;">{title}</p>'
        f'{sub_html}'
        f'<p style="margin:8px 0 0;font-size:14px;color:#555;">日期：{period}</p>'
        + address_block_html("地点：", addrs)
        + org_html
        + tag_html
        + img_html
        + "</section>"
    )


def render_html(items, title, lead):
    body = [home_link_html()]
    if lead:
        body.append(
            f'<p style="margin:0 0 16px;font-size:15px;color:#555;line-height:1.8;">'
            f"{html.escape(lead)}</p>"
        )
    for city, group in pick_city_group(items):
        body.append(
            f'<h2 style="font-size:17px;font-weight:bold;color:{ACCENT_DEEP};margin:22px 0 4px;'
            f'padding-left:10px;border-left:4px solid {ACCENT};">'
            f"{html.escape(city)} · {len(group)} 场</h2>"
        )
        for it in group:
            body.append(card_html(it))
    foot = (
        '<section style="margin-top:26px;padding-top:14px;border-top:1px dashed #ddd;">'
        f'<p style="font-size:13px;color:{MUTED};line-height:1.8;margin:0;">'
        "以上信息整理自公开渠道，具体以主办方现场公告为准。<br/>"
        f"想随时查附近正在进行的快闪，可以打开「{MP_NAME}」小程序看看。</p></section>"
    )
    body.append(foot)
    inner = "\n".join(body)
    return (
        f'<section style="font-size:15px;color:#333;line-height:1.75;padding:2px 4px;">\n'
        f"{inner}\n</section>"
    )


def render_md(items, title, lead):
    lines = [f"# {title}", ""]
    if MP_HOME_LINK:
        lines += [f"更多快闪内容可见小程序「{MP_NAME}」→ {MP_HOME_LINK}", ""]
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
