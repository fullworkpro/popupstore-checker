# data/inbox — 策展导入收件箱

把 WorkBuddy（或人工）产出的快闪 JSON 放进本目录，然后运行：

```bash
cd backend
python scripts/import_curated.py                 # 扫描并导入全部 *.json
python scripts/import_curated.py --dry-run       # 只预览不落库
```

导入成功的条目以 `status=DRAFT` 写入 `stores` 表，在后台「待发布」中可见，
人工审核确认后再发布。导入过的文件会自动移入 `done/`，不会重复导入。

## JSON 契约

完整字段说明见 `app/crawler/curated_importer.py` 顶部文档。最小可用示例：

```json
{
  "batch": "2026-09-10-shanghai",
  "items": [
    {
      "title": "《文豪野犬》三地快闪·上海站",
      "ip_name": "文豪野犬",
      "is_acg": true,
      "venue": "静安大悦城",
      "store_type": "popup",
      "city": "上海",
      "district": "静安区",
      "address": "静安大悦城北座1F",
      "start_date": "2026-09-25",
      "end_date": "2026-10-20",
      "organizer": "bilibiliGoods",
      "reservation": "required",
      "tags": ["文豪野犬", "漫画"],
      "source_url": "https://weibo.com/xxx/yyy",
      "confidence": 0.9
    }
  ]
}
```

## 去重规则

1. `source_url` 精确命中 → 跳过
2. 标题指纹（去标点/空格后比对）命中待发布中的同名条目 → 跳过
3. 其余 → 新增

无 `source_url` 时靠标题指纹去重，所以标题请保持稳定的官方写法。

## 注意

- 只有 `*.json` 会被扫描，`README.md` 与 `.example` 结尾的文件安全
- 日期支持 `YYYY-MM-DD`、`YYYY-MM-DD HH:MM:SS`、ISO 8601
- `confidence < 0.6` 的条目会标记 `needs_confirm`，审核时请重点核对
