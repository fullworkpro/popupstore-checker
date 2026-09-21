"""回归测试：push_wechat_draft.build_article 必须能正确解包 qrcode_bytes_for 的 3 元组。

背景：v1.4.16 起 qrcode_bytes_for() 返回 (bytes, ext, is_store_code)，
而 build_article 仍按 2 元组解包 → `ValueError: too many values to unpack`。
本测试把网络与外部凭据全部打桩，只验证解包与返回结构。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import push_wechat_draft as p  # noqa: E402


class _Resp:
    content = b"\xff\xd8\xff\xd9"  # 假 JPEG


class _FakeRequests:
    @staticmethod
    def get(url, timeout=60):
        return _Resp()


STORE = {
    "id": "abcdef1234567890",
    "title": "测试快闪",
    "subtitle": "副标题",
    "description": "描述文本",
    "cover_image": "https://example.com/a.jpg",
    "images": '["https://example.com/a.jpg","https://example.com/b.jpg"]',
    "cities": '[{"city":"广州","address":"天河路 1 号"}]',
    "tags": '["测试IP"]',
}


def main():
    p.requests = _FakeRequests
    # 打桩：专属码三元组 / 图片上传 / 封面上传
    p.qrcode_bytes_for = lambda sid=None: (b"\x89PNG\r\n", "png", True)
    p.upload_permanent_image = lambda wx, data, fn: "https://mmbiz.qpic.cn/x1"
    p.uploadimg = lambda wx, data, fn: "https://mmbiz.qpic.cn/x2"
    p.upload_thumb = lambda wx, data, fn: "thumb-media-id"
    p.archive_local = lambda d, fn, data: f"/tmp/{fn}"

    ok = 0

    # 1) 正常（上传）路径
    art, md, html = p.build_article(dict(STORE), "TOKEN", "260922", False, "", upload=True)
    assert isinstance(art, dict) and art["thumb_media_id"] == "thumb-media-id", "article 结构异常"
    assert "mmbiz.qpic.cn" in art["content"], "专属码未写进正文"
    assert isinstance(md, str) and isinstance(html, str), "返回值不是 (dict, md, html)"
    ok += 1
    print(f"PASS 1 上传路径：3 元组解包正常，专属码入正文（{len(art['content'])} 字节）")

    # 2) dry-run（不上传）路径
    art2, md2, html2 = p.build_article(dict(STORE), "", "260922", False, "", upload=False)
    assert art2["thumb_media_id"] == "", "dry-run 不应上传封面"
    ok += 1
    print("PASS 2 dry-run 路径：不上传素材但同样返回 3 元组")

    # 3) 无二维码（qrcode_bytes_for 返回 None）不应崩
    p.qrcode_bytes_for = lambda sid=None: None
    art3, _, _ = p.build_article(dict(STORE), "TOKEN", "260922", False, "", upload=True)
    assert isinstance(art3, dict)
    ok += 1
    print("PASS 3 无二维码降级：不抛异常")

    print(f"\n全部通过（{ok}/3）")


if __name__ == "__main__":
    main()
