"""微信素材图片格式归一化的回归测试 —— webp 等不支持格式必须转成 JPEG。

背景：图床/CDN 常返回 webp（URL 后缀却仍是 .jpg），直接上传会被微信拒
（40113 unsupported file type / 40137 invalid image format）。
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from PIL import Image  # noqa: E402

from gen_single_wechat import ensure_uploadable  # noqa: E402


def _make(fmt: str, mode: str = "RGB") -> bytes:
    im = Image.new(mode, (24, 24), (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30))
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def main() -> int:
    webp = _make("WEBP")
    webp_a = _make("WEBP", "RGBA")
    jpeg = _make("JPEG")
    png = _make("PNG")
    gif = _make("GIF")
    gif_bytes = _make("GIF", "P")

    checks = []

    data, name = ensure_uploadable(webp, "261016_图_1.jpg")
    checks.append(("webp 转为 JPEG 魔数", data[:2] == b"\xff\xd8"))
    checks.append(("webp 转后后缀为 .jpg", name.endswith(".jpg")))

    data_a, name_a = ensure_uploadable(webp_a, "261016_图_2.jpg")
    # 带透明通道的也要能转（白底铺底，不能报错或原样透传）
    checks.append(("webp(透明) 转为 JPEG", data_a[:2] == b"\xff\xd8" and name_a.endswith(".jpg")))

    d, n = ensure_uploadable(jpeg, "a.jpg")
    checks.append(("JPEG 原样返回", d == jpeg and n == "a.jpg"))
    d, n = ensure_uploadable(png, "b.png")
    checks.append(("PNG 原样返回", d == png and n == "b.png"))
    d, n = ensure_uploadable(gif, "c.gif")
    checks.append(("GIF 原样返回", d == gif and n == "c.gif"))
    d, n = ensure_uploadable(gif_bytes, "d.gif")
    checks.append(("GIF(P模式) 原样返回", d == gif_bytes and n == "d.gif"))

    # 非图片内容：转换失败也不能抛异常打断推送
    d, n = ensure_uploadable(b"not-an-image", "e.jpg")
    checks.append(("非图片内容安全透传", d == b"not-an-image" and n == "e.jpg"))

    # 转换结果确实能被 PIL 正常解码
    converted = ensure_uploadable(webp, "x.jpg")[0]
    try:
        Image.open(io.BytesIO(converted)).load()
        ok = True
    except Exception:
        ok = False
    checks.append(("转换结果可解码", ok))

    failed = 0
    for name_, ok_ in checks:
        print(("  ✓ " if ok_ else "  ✗ ") + name_)
        failed += 0 if ok_ else 1
    print(f"\n通过 {len(checks) - failed}/{len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
