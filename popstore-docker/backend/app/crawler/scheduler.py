"""爬虫调度器 — 统一调度所有数据源爬虫"""
import logging
from app.core.database import SessionLocal
from app.core.config import settings
from app.crawler.wechat_crawler import WechatCrawler
from app.crawler.xiaohongshu_crawler import XiaohongshuCrawler
from app.crawler.weibo_crawler import WeiboCrawler

logger = logging.getLogger("crawler.scheduler")


def run_all_crawlers() -> str:
    """运行所有已启用的爬虫，返回摘要"""
    db = SessionLocal()
    results = []

    try:
        # 微信公众号
        try:
            wc = WechatCrawler(db, accounts=settings.CRAWLER_WECHAT_ACCOUNTS)
            log = wc.run(settings.CRAWLER_KEYWORDS[:3])
            results.append(f"微信: {log.new_added} 新增 / {log.total_found} 发现")
        except Exception as e:
            logger.error(f"微信爬虫失败: {e}")
            results.append(f"微信: 失败 ({e})")

        # 小红书
        try:
            xhs = XiaohongshuCrawler(db)
            log = xhs.run(settings.CRAWLER_XHS_KEYWORDS[:2])
            results.append(f"小红书: {log.new_added} 新增 / {log.total_found} 发现")
        except Exception as e:
            logger.error(f"小红书爬虫失败: {e}")
            results.append(f"小红书: 失败 ({e})")

        # 微博
        try:
            wb = WeiboCrawler(db)
            log = wb.run(settings.CRAWLER_WEIBO_TOPICS[:2])
            results.append(f"微博: {log.new_added} 新增 / {log.total_found} 发现")
        except Exception as e:
            logger.error(f"微博爬虫失败: {e}")
            results.append(f"微博: 失败 ({e})")

    finally:
        db.close()

    summary = "; ".join(results)
    logger.info(f"爬虫执行完成: {summary}")
    return summary


def run_crawler_by_source(source: str) -> str:
    """单独运行某个数据源"""
    db = SessionLocal()
    try:
        if source == "wechat":
            crawler = WechatCrawler(db, accounts=settings.CRAWLER_WECHAT_ACCOUNTS)
            log = crawler.run(settings.CRAWLER_KEYWORDS[:3])
        elif source == "xiaohongshu":
            crawler = XiaohongshuCrawler(db)
            log = crawler.run(settings.CRAWLER_XHS_KEYWORDS[:2])
        elif source == "weibo":
            crawler = WeiboCrawler(db)
            log = crawler.run(settings.CRAWLER_WEIBO_TOPICS[:2])
        else:
            return f"未知数据源: {source}"

        return f"{source}: {log.new_added} 新增 / {log.total_found} 发现"
    finally:
        db.close()
