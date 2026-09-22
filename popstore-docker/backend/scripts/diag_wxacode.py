#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""店铺专属小程序码核查工具（v1.4.24）

用途：判断一篇已发布的公众号推文，文末那个码到底是「该店专属码」还是「通用码」，
并生成一张对照图给人眼复核。

为什么需要：CTA 文案从 v1.4.23 起不再区分专属码/通用码，只看文案判断不了；
而 dHash 单看"距离小"也不够 —— 必须带**对照组**（另一家店的码、通用码）才能下结论。

用法：
    python scripts/diag_wxacode.py --url https://mp.weixin.qq.com/s/XXXX --store-id <店铺ID>
    python scripts/diag_wxacode.py --url ... --store-id ... --title 备注   # 只比不抓

判定标准（dHash 32x32 汉明距离，两边统一转 JPEG 再比）：
    <= 10  同一张图
    >  100 不同图
实测：自家码 vs 自家重生成 3~4；不同店铺之间 174~202；与通用码 195+。

产出：data/outbox/qr_compare_<时间戳>.png（四格对照图，直接肉眼可辨）
"""
import argparse
import io
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from PIL import Image, ImageDraw  # noqa: E402

import gen_single_wechat as g  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CTA_RE = re.compile(r"<section[^>]*margin:26px[^>]*>")
IMG_RE = re.compile(r"https://mmbiz\.qpic\.cn/[^\"\s]+")


def dhash(img, n=32):
    gr = img.convert("L").resize((n + 1, n))
    px = list(gr.getdata())
    return [1 if px[y * (n + 1) + x] > px[y * (n + 1) + x + 1] else 0
            for y in range(n) for x in range(n)]


def ham(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def norm(data_or_im):
    im = data_or_im if isinstance(data_or_im, Image.Image) else Image.open(io.BytesIO(data_or_im))
    im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return Image.open(buf)


def article_code(url):
    """抓已发布文章，取文末 CTA 段里的码图"""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    m = CTA_RE.search(r.text)
    if not m:
        raise SystemExit("没找到文末 CTA 区块（margin:26px），文章结构可能变了")
    seg = r.text[m.start():m.start() + 1500]
    urls = IMG_RE.findall(seg)
    if not urls:
        raise SystemExit("CTA 段里没找到图片")
    b = requests.get(urls[-1], headers={"User-Agent": UA,
                                        "Referer": "https://mp.weixin.qq.com/"},
                     timeout=30).content
    return norm(b)


def _label_font(size=14):
    try:
        from PIL import ImageFont
        for f in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
            p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    except Exception:
        pass
    return None


def build_compare(tiles, out_path):
    """tiles: [(标题, PIL.Image), ...] → 一行多格对照图"""
    size = 220
    pad, top = 20, 36
    w = pad + len(tiles) * (size + pad)
    h = top + size + pad
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    font = _label_font()
    for i, (label, im) in enumerate(tiles):
        x = pad + i * (size + pad)
        for k, line in enumerate(label.split("\n")):
            d.text((x, 8 + k * 18), line, fill=(60, 52, 137), font=font)
        canvas.paste(im.resize((size, size)), (x, top))
    canvas.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="已发布推文 URL")
    ap.add_argument("--store-id", required=True, help="该文对应的店铺 ID")
    ap.add_argument("--ctrl-id", help="对照店铺 ID（另一家店，用于证明方法可区分）")
    args = ap.parse_args()

    os.makedirs(os.path.join("data", "outbox"), exist_ok=True)

    tiles = []
    hashes = {}

    if args.url:
        art = article_code(args.url)
        tiles.append(("文章里的码", art))
        hashes["文章里的码"] = dhash(art)

    pack = g.qrcode_bytes_for(args.store_id)
    if not pack:
        raise SystemExit("生成失败：未配小程序凭据或接口不可用")
    data, ext, is_store = pack
    print(f"重生成：ext={ext} is_store_code={is_store} bytes={len(data)}")
    own = norm(data)
    tiles.append((f"重生成 本店\n{args.store_id[:8]}", own))
    hashes["重生成 本店"] = dhash(own)

    if args.ctrl_id:
        cp = g.qrcode_bytes_for(args.ctrl_id)
        if cp:
            ctrl = norm(cp[0])
            tiles.append((f"对照组 另一店\n{args.ctrl_id[:8]}", ctrl))
            hashes["对照组 另一店"] = dhash(ctrl)

    gen_path = os.path.join("data", "assets", "xcx-qrcode.png")
    if os.path.exists(gen_path):
        generic = norm(open(gen_path, "rb").read())
        tiles.append(("通用码(本地)", generic))
        hashes["通用码(本地)"] = dhash(generic)

    print("\n汉明距离（<=10 同一张 / >100 不同）：")
    keys = list(hashes)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            d = ham(hashes[keys[i]], hashes[keys[j]])
            print(f"  {keys[i]:16s} vs {keys[j]:16s} = {d:4d}  "
                  f"{'同一张' if d <= 10 else '不同'}")

    out = os.path.join("data", "outbox", f"qr_compare_{int(time.time())}.png")
    build_compare(tiles, out)
    print(f"\n对照图已生成：{out}")


if __name__ == "__main__":
    main()
