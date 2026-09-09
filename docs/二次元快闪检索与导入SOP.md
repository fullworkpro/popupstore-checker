# 二次元快闪：WorkBuddy 检索 → 导入小程序 SQLite 库

> 适用版本：v1.4.5+ ｜ 最后更新：2026-09-10
> 目标：把 AI 检索到的快闪信息，**经人工审核**后进入小程序，避免脏数据直接上线。

## 一、整体链路

```
WorkBuddy 用 WebSearch / content-hunter 检索
        ↓  产出符合契约的结构化 JSON
backend/data/inbox/*.json   （收件箱）
        ↓  python scripts/import_curated.py
stores 表 status=DRAFT       （待发布队列，小程序不可见）
        ↓  后台人工审核 + 补全
status=PUBLISHED             （小程序可见）
```

**关键点**：导入的数据默认 `DRAFT`，小程序**看不到**，必须后台审核发布后才上线。

---

## 二、Step 1 — 在 WorkBuddy 里跑检索

WorkBuddy 里**不需要安装技能**，新开一个对话直接下指令即可（内置 WebSearch 工具）。

想抓小红书 / 抖音 / B站的快闪预告，可额外装 `content-hunter` 技能（`@` 唤起）。

### 可直接复制的提示词模板

```
请用 WebSearch 检索【最近一周内】国内【上海 / 广州】的二次元 / 动漫类
快闪店、特展、联名餐厅的【预告或正在举办】信息。

要求：
1. 优先找官方公告、场馆官微、品牌官微的信息，注明来源链接
2. 每条尽量拿到：标题、IP 名、场馆名、城市/区、详细地址、
   开始与结束日期、主办方、是否需要预约
3. 拿不到的字段留空，不要编造；日期不确定就标 needs_time
4. 按下面的 JSON 契约，把结果写入文件：
   E:\wingheart\Claw\workbuddy\acgnews\popstore-platform\backend\data\inbox\<YYYY-MM-DD>-<城市>.json
5. 不要改动仓库里的任何 .py / .vue / .js 代码

JSON 契约（完整字段说明见 backend/app/crawler/curated_importer.py 文件头）：
{
  "batch": "2026-09-10-shanghai",
  "items": [
    {
      "title": "《孤独摇滚》原画主题快闪",
      "ip_name": "孤独摇滚",
      "is_acg": true,
      "venue": "静安大悦城",
      "store_type": "popup",
      "city": "上海",
      "district": "静安区",
      "address": "静安大悦城南座3F",
      "start_date": "2026-09-04",
      "end_date": "2026-09-27",
      "organizer": "bilibiliGoods",
      "reservation": "required",
      "tags": ["孤独摇滚", "漫画"],
      "source_url": "https://weibo.com/xxx/yyy",
      "confidence": 0.9
    }
  ]
}

写完后告诉我文件路径和条目数。
```

### 提示词里的几个可调项

| 想调整 | 改哪里 |
|---|---|
| 换城市 | 「上海 / 广州」→ 任意城市（广州场馆：动漫星城、时尚天河、正佳广场、北京路） |
| 换时间窗 | 「最近一周」→ 「未来一个月」「本周末」 |
| 换类型 | `store_type`：`popup`（联名快闪）/ `exhibition`（特展）/ `restaurant`（联名餐厅） |
| 提高质量门槛 | 加一句「只保留 confidence ≥ 0.7 的条目」 |

---

## 三、Step 2 — 导入本地库（开发/试跑）

```bash
cd E:\wingheart\Claw\workbuddy\acgnews\popstore-platform\backend

python scripts/import_curated.py --dry-run     # 先预览，不落库
python scripts/import_curated.py               # 真正导入
python scripts/import_curated.py --no-archive  # 导入后保留原文件（便于重复试）
```

看到 `扫描 data\inbox：1 个文件，共 6 条，新增 6 条` 即成功。

---

## 四、Step 3 — 导入 NAS 线上库（真正生效）

### 前提：先重建一次镜像

v1.4.5 才把 `scripts/` 打进镜像，旧镜像里没有导入脚本：

```bash
cd /volume1/docker/popstore-platform   # 改成你的实际路径
docker compose -f compose.yml up -d --build backend
```

### 导入

compose 里 data 目录是挂载卷（`/volume1/docker/popstore-platform/data:/app/data`），
所以**只要把 JSON 丢进宿主机目录，容器里就能看到**，不用重建镜像：

```bash
# 1) 把 WorkBuddy 产出的 JSON 上传到 NAS：
#    /volume1/docker/popstore-platform/data/inbox/
#    （绿联云可用 File Station 直接上传，或用 scp）

# 2) 预览
docker exec popstore-backend python scripts/import_curated.py --dry-run

# 3) 导入
docker exec popstore-backend python scripts/import_curated.py
```

导入成功的 JSON 会自动移入 `data/inbox/done/`，不会重复导入。

---

## 五、Step 4 — 后台审核发布

1. 打开后台（NAS: `http://<NAS IP>:9115`）→ **待发布**
2. 逐条核对：标题、日期、地址、封面图
3. 重点看三类标记：
   - `needs_confirm`（confidence < 0.6）→ 信息存疑，务必核实
   - `needs_time` → 日期不全
   - `needs_address` → 地址缺失
4. 确认无误 → 发布 → 小程序可见

---

## 六、去重规则（避免重复数据）

按优先级依次判断，命中即跳过：

1. `source_url` 精确相同
2. 标题指纹（去掉标点/空格后相同）且原条目还在待发布中

**所以 `source_url` 尽量填**，能大幅提高去重准确度。

---

## 七、常见问题

**Q：导入报 `no such column: store_type`**
本地旧库（8/13 之前）缺列。跑一次自动迁移即可（幂等、无损）：
```bash
cd backend && python -c "import sys; sys.path.insert(0,'.'); from app.core.database import init_db; init_db()"
```
线上不用管 —— `main.py` 启动时会调 `init_db()`，容器重启后自动补齐。

**Q：小程序看不到导入的数据**
正常。导入是 `DRAFT` 状态，必须后台审核发布。

**Q：想批量删掉导入的测试数据**
后台「待发布」批量删除，或 `DELETE FROM stores WHERE source='curated';`

**Q：账号监控没抓到东西**
`venues.json` 里 21/22 个账号缺数字 UID，账号监控实际不生效。
补齐方式：后台「爬虫」页面填 UID，或编辑 `app/crawler/venues.json` 后重跑：
```bash
docker exec popstore-backend python scripts/seed_venues.py --apply
```
