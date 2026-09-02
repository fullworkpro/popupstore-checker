"""快闪店自动归档 — 结束日期早于今天的活动自动置为 archived，小程序端不再可见。

调用点（双保险）：
  1. scheduler：每日定时任务（即使无人访问小程序也会归档）
  2. mini.py 公开接口：请求级懒归档（带节流），保证小程序永远看不到已结束的活动
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.store import Store, StoreStatus

logger = logging.getLogger("popstore.archive")

# 业务时区固定 Asia/Shanghai。
# 注意：DB 中 start_date / end_date 均为「中国本地时间」的 naive datetime
# （后台日期选择器回传 'YYYY-MM-DD' → 补 T00:00:00 后入库），因此比较口径必须一致。
CN_TZ = timezone(timedelta(hours=8))

# 请求级懒归档的节流窗口（秒）：避免每个小程序请求都写一次库
_ARCHIVE_THROTTLE_SECONDS = 300
_last_archive_at = None


def now_cn() -> datetime:
    """当前中国本地时间（naive，与库中存储口径一致）。"""
    return datetime.now(CN_TZ).replace(tzinfo=None)


def today_start_cn() -> datetime:
    """「今天 00:00:00」的中国本地 naive datetime。"""
    n = datetime.now(CN_TZ)
    return datetime(n.year, n.month, n.day, 0, 0, 0, 0)


def archive_expired_stores(db: Session, force: bool = False) -> int:
    """把「已发布且结束日期 < 今天」的快闪店置为已归档，返回归档条数。

    force=True 时忽略节流（用于定时任务与后台手动触发）。
    """
    cutoff = today_start_cn()
    try:
        n = (
            db.query(Store)
            .filter(
                Store.status == StoreStatus.PUBLISHED.value,
                Store.end_date.isnot(None),
                Store.end_date < cutoff,
            )
            .update(
                {"status": StoreStatus.ARCHIVED.value, "updated_at": now_cn()},
                synchronize_session=False,
            )
        )
        if n:
            db.commit()
            logger.info("[archive] 已自动归档 %d 条已结束的快闪店（结束日期 < %s）",
                        n, cutoff.strftime("%Y-%m-%d"))
        _ = force  # force 仅用于语义标注，归档逻辑本身幂等
        return n
    except Exception as e:
        db.rollback()
        logger.warning("[archive] 自动归档失败: %s", e)
        return 0


def maybe_archive_expired(db: Session) -> int:
    """请求级懒归档：距上次执行超过节流窗口才真正跑一次。"""
    global _last_archive_at
    now = datetime.now(CN_TZ)
    if _last_archive_at is not None and (now - _last_archive_at).total_seconds() < _ARCHIVE_THROTTLE_SECONDS:
        return 0
    _last_archive_at = now
    return archive_expired_stores(db, force=True)
