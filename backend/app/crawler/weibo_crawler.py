"""微博爬虫（需登录 Cookie，此为框架占位）

实际使用时建议：
1. 配置有效的微博登录 Cookie
2. 使用 Playwright 模拟浏览器
3. 或通过微博开放平台 API（需审核）
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.crawler.base_crawler import BaseCrawler

logger = logging.getLogger("crawler.weibo")


class WeiboCrawler(BaseCrawler):
    source = "weibo"

    def __init__(self, db: Session, cookie: Optional[str] = None):
        super().__init__(db)
        self.cookie = cookie

    def fetch(self, keyword: str) -> List[Dict]:
        """
        注意：微博 Web 端搜索需要登录。
        此方法为框架占位，实际部署需要：
        - 使用 Playwright 模拟浏览器并保持登录态
        - 或接入微博开放平台 API
        """
        logger.warning(
            f"[weibo] 需要有效的登录 Cookie，关键词 '{keyword}' 返回空结果。"
            f"请在生产环境配置 Cookie 或使用 Playwright。"
        )
        return []
