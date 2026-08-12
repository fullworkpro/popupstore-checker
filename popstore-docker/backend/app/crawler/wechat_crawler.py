"""微信公众号爬虫（搜狗微信搜索已不可用，此为框架占位）

实际使用时建议：
1. 使用 Playwright 模拟浏览器访问微信公众号后台
2. 或接入第三方 API（新榜、微小宝等）
3. 或改为 RSS 订阅聚合 + 人工提交
"""
import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from app.crawler.base_crawler import BaseCrawler

logger = logging.getLogger("crawler.wechat")


class WechatCrawler(BaseCrawler):
    source = "wechat"

    def __init__(self, db: Session, accounts: List[str] = None):
        super().__init__(db)
        self.accounts = accounts or []

    def fetch(self, keyword: str) -> List[Dict]:
        """
        注意：搜狗微信搜索已于 2023 年停止服务。
        此方法为框架占位，实际部署需要替换为：
        - Playwright 自动化微信公众号后台
        - 或第三方 API（新榜、微小宝等）
        """
        logger.warning(
            f"[wechat] 搜狗微信搜索已不可用，关键词 '{keyword}' 返回空结果。"
            f"请在生产环境使用 Playwright 或第三方 API。"
        )
        # 返回示例结构以方便测试
        return [
            # {
            #     "title": "【快闪】XXX主题店限时开放",
            #     "description": "位于XX商场的二次元主题快闪店...",
            #     "cover_image": "",
            #     "city": "上海",
            #     "address": "XX商场B1",
            #     "start_date": None,
            #     "end_date": None,
            #     "organizer": "XXX品牌",
            #     "tags": '["快闪店","二次元"]',
            #     "source_url": "",
            # }
        ]
