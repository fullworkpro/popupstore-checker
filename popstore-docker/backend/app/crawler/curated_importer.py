"""人工/AI 策展导入器 — 把 WorkBuddy 产出的结构化快闪 JSON 写入待发布队列。

═══════════════════════════════════════════════════════════════
用途
═══════════════════════════════════════════════════════════════
后端不接 LLM，结构化抽取放在 WorkBuddy 侧完成（人工可读、可纠偏），
产出符合下述契约的 JSON，由本模块落库到 `stores` 表且 status=DRAFT，
进入后台「待发布」审核队列，人工确认后发布。

链路：WorkBuddy 检索 → 结构化 JSON → data/inbox/ → 本模块 → 待发布 → 发布

═══════════════════════════════════════════════════════════════
输入 JSON 契约
═══════════════════════════════════════════════════════════════
{
  "batch": "2026-09-10-shanghai",              // 可选，批次标识，入 crawl_meta
  "generated_at": "2026-09-10T00:00:00+08:00", // 可选
  "items": [
    {
      "title": "《孤独摇滚》原画主题快闪",      // 必填
      "subtitle": "",                          // 可选
      "description": "……",                     // 可选，正文/摘要
      "ip_name": "孤独摇滚",                    // 可选，进入 crawl_meta
      "is_acg": true,                          // 可选，是否严格二次元
      "venue": "静安大悦城",                    // 可选，场馆名
      "store_type": "popup",                   // 可选 popup|exhibition|restaurant
      "city": "上海",                           // 可选
      "district": "静安区",                     // 可选
      "address": "静安大悦城南座3F",            // 可选
      "start_date": "2026-09-04",              // 可选 YYYY-MM-DD 或 ISO 日期时间
      "end_date": "2026-09-27",                // 可选
      "organizer": "bilibiliGoods",            // 可选
      "reservation": "required",               // 可选 required|advance|no
      "tags": ["孤独摇滚", "漫画"],             // 可选，会自动补 "快闪"
      "source_url": "https://……",              // 强烈建议填，用于去重
      "cover_image": "",                       // 可选
      "confidence": 0.9,                       // 可选 0-1，<0.6 会标记待人工核实
      "needs_time": false,                     // 可选，true 时在后台提示待补全
      "needs_address": false                   // 可选
    }
  ]
}

去重优先级：source_url 精确命中 → 标题指纹（去标点空格后比对）→ 新增。
无 source_url 的条目靠标题指纹去重，因此标题请保持稳定的官方写法。

═══════════════════════════════════════════════════════════════
用法
═══════════════════════════════════════════════════════════════
    python scripts/import_curated.py                     # 扫描 data/inbox/*.json
    python scripts/import_curated.py path/to/file.json   # 导入单个文件
    python scripts/import_curated.py --dry-run           # 只预览不落库
"""
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.crawler.base_crawler import BaseCrawler
from app.models.store import Store, StoreStatus, CrawlLog

logger = logging.getLogger("crawler.curated")

# 批次归档目录：导入成功的 JSON 会移到这里，避免重复导入
INBOX_DIR = os.path.join("data", "inbox")
DONE_DIR = os.path.join(INBOX_DIR, "done")

_PUNCT = re.compile(r"[\s　,，。.、!！?？:：;；\"'“”‘’()（）\[\]【】《》\-—_/\\|]+")


def title_fingerprint(title: str) -> str:
    """标题指纹：去标点/空白/大小写，用于无 URL 时的去重。"""
    return _PUNCT.sub("", (title or "").strip()).lower()


def parse_dt(value) -> Optional[datetime]:
    """接受 date / datetime / 'YYYY-MM-DD' / ISO 字符串；失败返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        logger.warning("[curated] 无法解析日期：%r", value)
        return None


class CuratedImporter(BaseCrawler):
    """策展导入器 — 复用 BaseCrawler 的落库流程，但去重扩展到标题指纹。"""

    source = "curated"

    def fetch(self, keyword: str) -> List[Dict]:
        """兼容基类接口：keyword 视为 JSON 文件路径，读取并返回原始条目。"""
        return load_items(keyword)

    # ── 去重入库（覆盖基类：URL 去重 + 标题指纹去重）──
    def save_items(self, items: List[Dict]) -> int:
        new_count = 0
        for item in items:
            url = (item.get("source_url") or "").strip()
            title = (item.get("title") or "").strip()[:200] or "无标题"
            fp = title_fingerprint(title)

            hit = None
            if url:
                hit = self.db.query(Store).filter(Store.source_url == url).first()
            if hit is None and fp:
                # 标题指纹去重：加载候选标题逐个比对（数据量小，可接受）
                cands = (
                    self.db.query(Store)
                    .filter(Store.status == StoreStatus.DRAFT.value)
                    .all()
                )
                for c in cands:
                    if title_fingerprint(c.title) == fp:
                        hit = c
                        break
            if hit is not None:
                logger.info("[curated] 跳过已存在：%s", title)
                continue

            store = Store(
                title=title,
                subtitle=item.get("subtitle", "") or "",
                description=item.get("description", "") or "",
                cover_image=item.get("cover_image", "") or "",
                images=item.get("images", "[]"),
                cities=item.get("cities", "[]"),
                city=item.get("city", "") or "",
                district=item.get("district", "") or "",
                address=item.get("address", "") or "",
                start_date=parse_dt(item.get("start_date")),
                end_date=parse_dt(item.get("end_date")),
                organizer=item.get("organizer", "") or "",
                reservation=item.get("reservation", "no") or "no",
                store_type=item.get("store_type") or "popup",
                tags=item.get("tags", "[]"),
                source=self.source,
                source_url=url,
                status=StoreStatus.DRAFT.value,
                crawl_meta=item.get("crawl_meta", "{}") or "{}",
            )
            self.db.add(store)
            new_count += 1
        if new_count:
            self.db.commit()
        return new_count


def load_items(path: str) -> List[Dict]:
    """读取 JSON 文件，返回 items 列表（兼容 {items:[...]} 与裸列表两种写法）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    raise ValueError(f"不支持的 JSON 结构：{path}")


def normalize(item: Dict, batch: str = "") -> Dict:
    """把 WorkBuddy 的条目字段映射成 Store 入库字段（不做 LLM 抽取，只做格式化）。"""
    title = (item.get("title") or "").strip()[:200] or "无标题"

    tags = list(item.get("tags") or [])
    ip_name = (item.get("ip_name") or "").strip()
    venue = (item.get("venue") or "").strip()
    if ip_name and ip_name not in tags:
        tags.append(ip_name)
    if venue and venue not in tags:
        tags.append(venue)
    if "快闪" not in tags:
        tags.append("快闪")

    city = (item.get("city") or "").strip()
    district = (item.get("district") or "").strip()
    address = (item.get("address") or "").strip()
    cities_json = json.dumps(
        ([{"city": city, "district": district, "address": address}] if city else []),
        ensure_ascii=False,
    )

    confidence = item.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    meta = {
        "batch": batch,
        "ip_name": ip_name,
        "venue": venue,
        "is_acg": bool(item.get("is_acg", False)),
        "confidence": confidence,
        "needs_time": bool(item.get("needs_time", item.get("start_date") is None)),
        "needs_address": bool(item.get("needs_address", address == "")),
        "needs_confirm": bool(confidence is not None and confidence < 0.6),
        "images_need_upload": True,
        "raw_text": (item.get("description") or "")[:2000],
    }

    return {
        "title": title,
        "subtitle": item.get("subtitle", "") or "",
        "description": item.get("description", "") or "",
        "cover_image": item.get("cover_image", "") or "",
        "images": "[]",
        "cities": cities_json,
        "city": city,
        "district": district,
        "address": address,
        "start_date": item.get("start_date"),
        "end_date": item.get("end_date"),
        "organizer": item.get("organizer", "") or "",
        "reservation": item.get("reservation", "no") or "no",
        "store_type": item.get("store_type") or "popup",
        "tags": json.dumps(tags, ensure_ascii=False),
        "source_url": (item.get("source_url") or "").strip(),
        "crawl_meta": json.dumps(meta, ensure_ascii=False),
    }


def import_file(db: Session, path: str, archive: bool = True,
                dry_run: bool = False) -> Tuple[int, int, List[str]]:
    """导入单个 JSON 文件。返回 (总条数, 新增条数, 错误列表)。"""
    errors: List[str] = []
    try:
        raw_items = load_items(path)
    except Exception as e:
        return 0, 0, [f"读取失败 {path}: {e}"]

    batch = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = json.load(f)
        if isinstance(head, dict):
            batch = head.get("batch") or os.path.splitext(os.path.basename(path))[0]
    except Exception:
        batch = os.path.splitext(os.path.basename(path))[0]

    normalized = []
    for i, it in enumerate(raw_items):
        try:
            if not (it or {}).get("title"):
                errors.append(f"#{i} 缺少 title，已跳过")
                continue
            normalized.append(normalize(it, batch))
        except Exception as e:
            errors.append(f"#{i} 解析失败: {e}")

    if dry_run:
        for n in normalized:
            logger.info("[curated][dry-run] %s | %s | %s", n["city"], n["title"], n["start_date"])
        return len(raw_items), 0, errors

    importer = CuratedImporter(db)
    added = importer.save_items(normalized)

    log = CrawlLog(
        source=CuratedImporter.source,
        keyword=batch[:100],
        total_found=len(raw_items),
        new_added=added,
        error_count=len(errors),
        error_detail="\n".join(errors),
        status="failed" if errors and not added else ("partial" if errors else "success"),
    )
    db.add(log)
    db.commit()
    logger.info("[curated] %s：%d 条，新增 %d 条", path, len(raw_items), added)

    if archive:
        try:
            os.makedirs(DONE_DIR, exist_ok=True)
            shutil.move(path, os.path.join(DONE_DIR, os.path.basename(path)))
        except Exception as e:
            logger.warning("[curated] 归档失败（不影响入库）：%s", e)

    return len(raw_items), added, errors


def import_inbox(db: Session, inbox: str = INBOX_DIR, archive: bool = True,
                 dry_run: bool = False) -> Dict:
    """扫描 inbox 目录下所有 .json 并导入。返回汇总统计。"""
    if not os.path.isdir(inbox):
        return {"files": 0, "total": 0, "added": 0, "errors": [f"目录不存在：{inbox}"]}

    files = sorted(
        os.path.join(inbox, f) for f in os.listdir(inbox)
        if f.lower().endswith(".json") and os.path.isfile(os.path.join(inbox, f))
    )
    summary = {"files": len(files), "total": 0, "added": 0, "errors": []}
    for p in files:
        total, added, errs = import_file(db, p, archive=archive, dry_run=dry_run)
        summary["total"] += total
        summary["added"] += added
        summary["errors"].extend(errs)
    return summary
