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

## 多城市 / 多地址写法（推荐）

一个活动在多城巡回时，**不要拆成多条**（标题会雷同、去重易误判），
改用 `cities` 数组，一条记录承载全部地点：

```json
{
  "title": "三丽鸥全国巡展",
  "store_type": "popup",
  "cities": [
    { "city": "上海", "district": "静安区", "address": "静安大悦城 3F" },
    { "city": "广州", "district": "天河区", "address": "正佳广场 1F" },
    { "city": "成都", "district": "锦江区", "address": "IFS 5F" }
  ],
  "start_date": "2026-09-25",
  "end_date": "2026-10-20",
  "source_url": "https://weibo.com/xxx/yyy"
}
```

也支持只写城市名（地址后续人工补）：`"cities": ["上海", "广州"]`

- `cities[0]` 自动作为**主城市 / 主地址**（`Store.city` / `district` / `address`），
  保证城市筛选和详情页「地点1」正常
- 小程序详情页会依次列出「地点1 / 地点2 …」
- 城市筛选命中任一地点都会被搜到（后端 `city == 值 OR cities LIKE %值%`）
- 旧的 `"city" + "district" + "address"` 单值写法**仍然支持**；两者同时给时以 `cities` 为准
- 只有 1 个地点时，顶层 `district` / `address` 会自动回填补全

## store_type 快闪类型取值

| JSON 里填 | 中文显示 | 适用 |
|---|---|---|
| `popup`（默认，可省略） | 联名快闪 | IP 联名、限时快闪店、周边贩售 |
| `exhibition` | 特展 | 展览、展映、艺术展、纪念展 |
| `restaurant` | 联名餐厅 | 主题餐厅、咖啡厅、联名餐饮 |

填错或不填都按 `popup` 处理。判断困难时按**主要业态**选：
以卖周边为主 → `popup`；以观展为主 → `exhibition`；以堂食饮品为主 → `restaurant`。

## 去重规则

1. `source_url` 精确命中 → 跳过
2. 标题指纹（去标点/空格后比对）命中待发布中的同名条目 → 跳过
3. 其余 → 新增

无 `source_url` 时靠标题指纹去重，所以标题请保持稳定的官方写法。

## 注意

- 只有 `*.json` 会被扫描，`README.md` 与 `.example` 结尾的文件安全
- 日期支持 `YYYY-MM-DD`、`YYYY-MM-DD HH:MM:SS`、ISO 8601
- `confidence < 0.6` 的条目会标记 `needs_confirm`，审核时请重点核对
