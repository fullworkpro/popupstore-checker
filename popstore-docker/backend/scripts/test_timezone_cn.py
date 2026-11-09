"""时区回归：所有展示用时间戳必须输出带 +08:00 的北京时间。

背景：SQLAlchemy 的 DateTime 列（未开 timezone=True）落库会丢 tzinfo，
Store / CrawlLog 等以 datetime.now(timezone.utc) 写入，读回来是「朴素 UTC」；
而爬虫运行态 last_run_at / last_success_at 用 datetime.now() 写入，
容器 TZ=Asia/Shanghai，是「朴素北京时间」。两者不能混用同一转换。

运行：python scripts/test_timezone_cn.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.store import (  # noqa: E402
    Store, CrawlLog, CrawlerState, CrawlerConfig,
    utc_naive_to_cn_iso, cn_naive_to_cn_iso,
)
from app.schemas.schemas import StoreResponse, CrawlLogResponse  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {name} {extra}")


UTC_NAIVE = datetime(2026, 11, 9, 0, 0, 0)      # 库里实际值 = 北京 08:00
CN_NAIVE = datetime(2026, 11, 9, 8, 0, 0)       # 运行态实际值 = 北京 08:00
EXPECTED = "2026-11-09T08:00:00+08:00"

print("== 1) 两种朴素时间的转换函数 ==")
check("UTC-naive 转 +08 且时刻 +8h", utc_naive_to_cn_iso(UTC_NAIVE) == EXPECTED,
      utc_naive_to_cn_iso(UTC_NAIVE))
check("CN-naive 只补时区，时刻不变", cn_naive_to_cn_iso(CN_NAIVE) == EXPECTED,
      cn_naive_to_cn_iso(CN_NAIVE))
check("CN-naive 误用 UTC 转换会多 8h（防止误改）",
      utc_naive_to_cn_iso(CN_NAIVE) == "2026-11-09T16:00:00+08:00")
check("None 安全", utc_naive_to_cn_iso(None) is None and cn_naive_to_cn_iso(None) is None)
check("带 tz 的 UTC 输入也能正确换算",
      utc_naive_to_cn_iso(datetime(2026, 11, 9, 0, 0, 0, tzinfo=__import__('datetime').timezone.utc)) == EXPECTED)

print("== 2) StoreResponse（后台列表/详情/仪表盘、小程序共用）==")
store = StoreResponse(
    id="x", title="t", status="published", view_count=0, share_count=0,
    created_at=UTC_NAIVE, updated_at=UTC_NAIVE, reviewed_at=UTC_NAIVE,
    start_date=datetime(2026, 10, 1, 0, 0, 0),
    end_date=datetime(2026, 10, 20, 0, 0, 0),
)
j = json.loads(store.model_dump_json())
for field in ("created_at", "updated_at", "reviewed_at"):
    check(f"{field} 带 +08:00 且时刻正确", j[field] == EXPECTED, j[field])
check("start_date 是纯日期、不受时区转换影响",
      j["start_date"].startswith("2026-10-01T00:00:00") and "+08" not in j["start_date"],
      j["start_date"])
check("end_date 是纯日期、不受时区转换影响",
      j["end_date"].startswith("2026-10-20T00:00:00") and "+08" not in j["end_date"],
      j["end_date"])
check("空时间戳返回 None",
      json.loads(StoreResponse(id="y", title="t", status="draft", view_count=0,
                               share_count=0).model_dump_json())["created_at"] is None)

print("== 3) CrawlLogResponse（爬取日志）==")
log = CrawlLogResponse(
    id="1", source="weibo", keyword="k", total_found=0, new_added=0,
    error_count=0, error_detail="", status="success", created_at=UTC_NAIVE,
)
check("日志时间带 +08:00", json.loads(log.model_dump_json())["created_at"] == EXPECTED)

print("== 4) to_dict() 各模型（防止将来直接调用时又漏时区）==")
s = Store(id="s", title="t", created_at=UTC_NAIVE, updated_at=UTC_NAIVE)
check("Store.to_dict created_at", s.to_dict()["created_at"] == EXPECTED)
check("Store.to_dict updated_at", s.to_dict()["updated_at"] == EXPECTED)

st = CrawlerState(source="weibo", last_run_at=CN_NAIVE, last_success_at=CN_NAIVE,
                  updated_at=UTC_NAIVE)
check("CrawlerState.last_run_at 不被多转 8h", st.to_dict()["last_run_at"] == EXPECTED,
      st.to_dict()["last_run_at"])
check("CrawlerState.last_success_at 不被多转 8h", st.to_dict()["last_success_at"] == EXPECTED)
check("CrawlerState.updated_at 按 UTC 转", st.to_dict()["updated_at"] == EXPECTED)

cfg = CrawlerConfig(key="global", created_at=UTC_NAIVE, updated_at=UTC_NAIVE)
check("CrawlerConfig.created_at", cfg.to_dict()["created_at"] == EXPECTED)
check("CrawlerConfig.updated_at", cfg.to_dict()["updated_at"] == EXPECTED)

cl = CrawlLog(id="l", source="weibo", created_at=UTC_NAIVE)
check("CrawlLog.to_dict", cl.to_dict()["created_at"] == EXPECTED)

print(f"\n结果: 通过 {PASS} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
