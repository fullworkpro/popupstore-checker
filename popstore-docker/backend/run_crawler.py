#!/usr/bin/env python3
"""独立爬虫运行脚本 — 供 crontab 调用"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.crawler.scheduler import run_all_crawlers

if __name__ == "__main__":
    result = run_all_crawlers()
    print(f"[{__file__}] {result}")
