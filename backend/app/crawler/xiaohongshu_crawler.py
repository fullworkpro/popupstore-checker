"""小红书爬虫（需登录 Cookie，此为框架占位）

实际使用时建议：
1. 配置有效的小红书登录 Cookie
2. 使用 Playwright 模拟浏览器
3. 或接入第三方小红书数据 API
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.crawler.base_crawler import BaseCrawler

logger = logging.getLogger("crawler.xiaohongshu")


class XiaohongshuCrawler(BaseCrawler):
    source = "xiaohongshu"

    def __init__(self, db: Session, cookie: Optional[str] = None):
        super().__init__(db)
        self.cookie = cookie

    def fetch(self, keyword: str) -> List[Dict]:
        """
        注意：小红书 Web 端需要登录 Cookie 才能搜索。
        此方法为框架占位，实际部署需要：
        - 使用 Playwright 模拟浏览器并保持登录态
        - 或通过手机抓包获取 API 接口和 Cookie
        """
        logger.warning(
            f"[xiaohongshu] 需要有效的登录 Cookie，关键词 '{keyword}' 返回空结果。"
            f"请在生产环境配置 Cookie 或使用 Playwright。"
        )
        return []
