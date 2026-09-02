"""爬虫调度器 — 统一调度所有数据源爬虫，配置来自数据库（CrawlerConfig 单例）。

- 定时任务在应用启动时依据「数据库中的 schedule」注册；
- 每次执行时再读取 enabled 开关，disabled 则跳过；
- 前端修改配置后调用 sync_scheduler() 实时调整任务（增删/启停）。
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.core.config import settings
from app.crawler.config_store import get_or_create_config
from app.crawler.wechat_crawler import WechatCrawler
from app.crawler.xiaohongshu_crawler import XiaohongshuCrawler
from app.crawler.weibo_crawler import WeiboCrawler
from app.services.archive import archive_expired_stores

logger = logging.getLogger("crawler.scheduler")

# 调度器实例（时区固定 Asia/Shanghai，与用户所在时区一致）
crawler_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

# 并发锁：防止「手动触发」与「定时任务」重叠导致的双倍请求速率（会放大限流 -100）
import threading
_crawl_lock = threading.Lock()

_JOB_PREFIX = "crawl_"  # 任务 id 前缀，便于批量移除

# 归档任务独立 id：不以 crawl_ 开头，因此不会被 _register_jobs 的清理逻辑误删。
# 归档与爬虫无关——即使爬虫总开关关闭，已结束的活动也必须每天归档。
_ARCHIVE_JOB_ID = "archive_expired_stores"
_ARCHIVE_HOUR = 3
_ARCHIVE_MINUTE = 15


def run_archive() -> int:
    """每日归档：把「已发布且结束日期 < 今天」的快闪店置为已归档。"""
    db = SessionLocal()
    try:
        n = archive_expired_stores(db, force=True)
        if n:
            logger.info("🗄️ 每日归档完成：%d 条已结束快闪店已归档（小程序不可见）", n)
        return n
    except Exception as e:
        logger.error("⚠️ 每日归档失败: %s", e)
        return 0
    finally:
        db.close()


def _weibo_from_config(db, cfg: "object") -> WeiboCrawler:
    import json
    keywords = json.loads(cfg.weibo_keywords) if isinstance(cfg.weibo_keywords, str) else cfg.weibo_keywords
    accounts = json.loads(cfg.weibo_accounts) if isinstance(cfg.weibo_accounts, str) else cfg.weibo_accounts
    return WeiboCrawler(
        db,
        keywords=keywords,
        accounts=accounts,
        cookie=cfg.weibo_cookie or None,
        lookback_days=cfg.lookback_days,
        max_pages=cfg.weibo_max_pages,
        # 两种模式独立开关；均为 None（列刚补、未回填）时由 crawler 侧取 settings 默认
        uid_enabled=cfg.weibo_uid_enabled,
        keyword_enabled=cfg.weibo_keyword_enabled,
    )


def run_all_crawlers() -> str:
    """运行所有已启用的爬虫，返回摘要。配置以数据库为准。

    非阻塞安全：若上一次仍在运行（持锁），直接跳过，避免叠加请求放大限流。
    """
    if not _crawl_lock.acquire(blocking=False):
        logger.warning("⏳ 上一次爬虫任务仍在运行，本次（全量）自动跳过")
        return "已有爬虫任务运行中，已跳过"
    db = SessionLocal()
    results = []
    try:
        cfg = get_or_create_config(db)
        if not cfg.enabled:
            logger.info("⏸️ 爬虫总开关已关闭（前端配置），本次定时任务跳过")
            return "爬虫已禁用（前端配置关闭）"

        # 微信公众号（占位源，目前返回空）
        try:
            wc = WechatCrawler(db, accounts=settings.CRAWLER_WECHAT_ACCOUNTS)
            log = wc.run(settings.CRAWLER_KEYWORDS[:3])
            results.append(f"微信: {log.new_added} 新增 / {log.total_found} 发现")
        except Exception as e:
            logger.error(f"微信爬虫失败: {e}")
            results.append(f"微信: 失败 ({e})")

        # 小红书（规划中，尚未实现爬虫；若用户在页面开启则给出提示并跳过）
        if cfg.xhs_enabled:
            logger.info("小红书爬虫尚未实现（待微博验证通过后开放），本次跳过")
            results.append("小红书: 暂未实现（跳过）")
        else:
            results.append("小红书: 未启用")

        # 抖音（规划中，同上）
        if cfg.douyin_enabled:
            logger.info("抖音爬虫尚未实现（待微博验证通过后开放），本次跳过")
            results.append("抖音: 暂未实现（跳过）")
        else:
            results.append("抖音: 未启用")

        # 微博（全站搜索原创二次元快闪微博，配置来自数据库）
        try:
            wb = _weibo_from_config(db, cfg)
            log = wb.run()
            results.append(f"微博: {log.new_added} 新增 / {log.total_found} 发现")
        except Exception as e:
            logger.error(f"微博爬虫失败: {e}")
            results.append(f"微博: 失败 ({e})")

    finally:
        db.close()
        _crawl_lock.release()

    summary = "; ".join(results)
    logger.info(f"爬虫执行完成: {summary}")
    return summary


def run_weibo_only() -> str:
    """仅运行微博爬虫（前端「手动触发微博」按钮调用），返回摘要。

    手动触发与定时任务共用同一把锁，二者不会重叠，避免双倍请求速率放大限流。
    """
    if not _crawl_lock.acquire(blocking=False):
        logger.warning("⏳ 上一次爬虫任务仍在运行，本次（仅微博）自动跳过")
        return "已有爬虫任务运行中，已跳过"
    db = SessionLocal()
    try:
        cfg = get_or_create_config(db)
        wb = _weibo_from_config(db, cfg)
        log = wb.run()
        result = f"微博: {log.new_added} 新增 / {log.total_found} 发现"
        logger.info(f"仅微博爬虫执行完成: {result}")
        return result
    except Exception as e:
        logger.error(f"仅微博爬虫失败: {e}")
        return f"微博: 失败 ({e})"
    finally:
        db.close()
        _crawl_lock.release()


def run_crawler_by_source(source: str) -> str:
    """单独运行某个数据源"""
    db = SessionLocal()
    try:
        if source == "wechat":
            crawler = WechatCrawler(db, accounts=settings.CRAWLER_WECHAT_ACCOUNTS)
            log = crawler.run(settings.CRAWLER_KEYWORDS[:3])
        elif source == "xiaohongshu":
            return "小红书爬虫尚未实现（规划中）"
        elif source == "douyin":
            return "抖音爬虫尚未实现（规划中）"
        elif source == "weibo":
            cfg = get_or_create_config(db)
            crawler = _weibo_from_config(db, cfg)
            log = crawler.run()
        else:
            return f"未知数据源: {source}"

        return f"{source}: {log.new_added} 新增 / {log.total_found} 发现"
    finally:
        db.close()


def _register_jobs(cfg) -> None:
    """按配置中的 schedule 注册定时任务（先清空旧任务）。"""
    for job in crawler_scheduler.get_jobs():
        if job.id.startswith(_JOB_PREFIX):
            crawler_scheduler.remove_job(job.id)
    if not cfg.enabled:
        logger.info("⏸️ 爬虫已禁用，不注册定时任务")
        return
    import json
    times = json.loads(cfg.schedule) if isinstance(cfg.schedule, str) else cfg.schedule
    for t in times:
        try:
            hh, mm = str(t).split(":")
            crawler_scheduler.add_job(
                run_all_crawlers,
                CronTrigger(hour=int(hh), minute=int(mm)),
                id=f"{_JOB_PREFIX}{t}",
                replace_existing=True,
                misfire_grace_time=3600,
            )
        except Exception as e:
            logger.error("⚠️ 爬虫定时任务注册失败 %s: %s", t, e)
    logger.info("⏰ 爬虫定时任务已注册: %s（时区 Asia/Shanghai）", times)


def _register_archive_job() -> None:
    """注册每日归档定时任务（独立于爬虫开关）。"""
    try:
        crawler_scheduler.add_job(
            run_archive,
            CronTrigger(hour=_ARCHIVE_HOUR, minute=_ARCHIVE_MINUTE),
            id=_ARCHIVE_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("🗄️ 归档定时任务已注册: 每日 %02d:%02d（时区 Asia/Shanghai）",
                    _ARCHIVE_HOUR, _ARCHIVE_MINUTE)
    except Exception as e:
        logger.error("⚠️ 归档定时任务注册失败: %s", e)


def init_scheduler() -> None:
    """应用启动：依据数据库配置初始化调度器。"""
    db = SessionLocal()
    try:
        cfg = get_or_create_config(db)
        _register_jobs(cfg)
        _register_archive_job()
        if not crawler_scheduler.running:
            crawler_scheduler.start()
    finally:
        db.close()

    # 启动即归档一次：NAS 可能关机多日，避免等待凌晨定时任务才清理过期活动
    try:
        run_archive()
    except Exception as e:
        logger.warning("⚠️ 启动时归档失败: %s", e)


def sync_scheduler(db) -> None:
    """前端修改配置后调用：依据最新配置重建定时任务。"""
    cfg = get_or_create_config(db)
    _register_jobs(cfg)
    _register_archive_job()
    # 注意：即使爬虫总开关关闭，调度器也必须运行——归档任务挂在同一个调度器上。
    # （爬虫任务本身由 _register_jobs 在 enabled=False 时不注册来跳过）
    if not crawler_scheduler.running:
        crawler_scheduler.start()


def shutdown_scheduler() -> None:
    if crawler_scheduler.running:
        crawler_scheduler.shutdown(wait=False)
