"""清理微信公众号素材库里的重复图片（同名文件多份）。

背景：推送跑到一半失败后重跑，已上传成功的那些图会被再传一遍，
素材库里就出现两张一模一样的图、白白占配额。本脚本按文件名分组，
重复的只保留最新一份，其余删掉。

用法：
    python scripts/clean_wx_materials.py             # 只列出重复项（不删）
    python scripts/clean_wx_materials.py --apply     # 确认后真删（保留最新一份）
    python scripts/clean_wx_materials.py --max 800   # 回扫最近 800 条（默认 400）

安全：只处理素材名重复的文件；正文正在引用的 URL 属于保留那份，不受影响。
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_single_wechat import get_access_token  # noqa: E402

API = "https://api.weixin.qq.com/cgi-bin"


def list_images(token: str, max_items: int):
    """回扫图片素材，返回 [(media_id, name, url)]（微信按时间倒序返回）"""
    out, off = [], 0
    while off < max_items:
        r = requests.post(
            f"{API}/material/batchget_material?access_token={token}",
            json={"type": "image", "offset": off, "count": 20},
            timeout=40,
        ).json()
        if r.get("errcode"):
            print(f"[错误] 拉取素材失败: {r}")
            break
        items = r.get("item") or []
        out += [(i.get("media_id"), i.get("name") or "", i.get("url") or "") for i in items]
        if len(items) < 20:
            break
        off += len(items)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真删（默认只列出）")
    ap.add_argument("--max", type=int, default=400)
    args = ap.parse_args()

    token = get_access_token()
    items = list_images(token, args.max)
    print(f"[素材] 回扫到 {len(items)} 张图片素材")

    first = {}  # name -> (media_id, url) 最新的一条
    dups = []   # 需要删除的 (media_id, name)
    for mid, name, url in items:
        if not name:
            continue
        if name in first:
            dups.append((mid, name))
        else:
            first[name] = (mid, url)

    if not dups:
        print("[结果] 没有重复素材，素材库是干净的 ✅")
        return

    print(f"[结果] 发现 {len(dups)} 个重复素材（涉及 {len(set(n for _, n in dups))} 个文件名）：")
    for mid, name in dups[:30]:
        print(f"  - {name}  ({mid})")
    if len(dups) > 30:
        print(f"  ... 还有 {len(dups) - 30} 条")

    if not args.apply:
        print("\n（只列出未删除；确认无误后加 --apply 执行删除）")
        return

    ok = fail = 0
    for mid, name in dups:
        r = requests.post(
            f"{API}/material/del_material?access_token={token}",
            json={"media_id": mid},
            timeout=40,
        ).json()
        if r.get("errcode") == 0:
            ok += 1
        else:
            fail += 1
            print(f"  [删除失败] {name}: {r}")
    print(f"\n✅ 清理完成：删除 {ok} 条，失败 {fail} 条")


if __name__ == "__main__":
    main()
