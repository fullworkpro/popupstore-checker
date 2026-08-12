"""爬虫基类 — 定义通用爬虫接口"""
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.store import Store, StoreStatus, CrawlLog

logger = logging.getLogger("crawler")


class BaseCrawler(ABC):
    """爬虫基类，所有数据源爬虫继承此类"""

    source: str = "crawler"

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def fetch(self, keyword: str) -> List[Dict]:
        """执行抓取，返回标准化字典列表"""
        ...

    def run(self, keywords: List[str]) -> CrawlLog:
        """执行爬取 + 去重入库"""
        crawl_log = CrawlLog(
            source=self.source,
            keyword=",".join(keywords[:3]),
            total_found=0,
            new_added=0,
            error_count=0,
            status="success",
        )

        all_items: List[Dict] = []
        errors: List[str] = []

        for kw in keywords:
            try:
                items = self.fetch(kw)
                all_items.extend(items)
                logger.info(f"[{self.source}] 关键词 '{kw}' 抓取到 {len(items)} 条")
            except Exception as e:
                errors.append(f"[{kw}] {str(e)}")
                logger.error(f"[{self.source}] 关键词 '{kw}' 抓取失败: {e}")

        crawl_log.total_found = len(all_items)
        crawl_log.error_count = len(errors)
        crawl_log.error_detail = "\n".join(errors) if errors else ""
        crawl_log.status = "failed" if len(errors) == len(keywords) else ("partial" if errors else "success")

        # 去重入库
        new_count = 0
        for item in all_items:
            url_hash = self._hash_url(item.get("source_url", ""))
            exists = (
                self.db.query(Store)
                .filter(Store.source_url.contains(item.get("source_url", "")[:200]))
                .first()
            )
            if not exists:
                store = Store(
                    title=item.get("title", "无标题")[:200],
                    description=item.get("description", ""),
                    cover_image=item.get("cover_image", ""),
                    city=item.get("city", ""),
                    address=item.get("address", ""),
                    start_date=item.get("start_date"),
                    end_date=item.get("end_date"),
                    organizer=item.get("organizer", ""),
                    tags=item.get("tags", "[]"),
                    source=self.source,
                    source_url=item.get("source_url", ""),
                    status=StoreStatus.DRAFT.value,
                )
                self.db.add(store)
                new_count += 1

        self.db.add(crawl_log)
        self.db.commit()

        crawl_log.new_added = new_count
        self.db.commit()

        logger.info(f"[{self.source}] 总计 {len(all_items)} 条，新增 {new_count} 条")
        return crawl_log

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()
