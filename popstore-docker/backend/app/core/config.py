"""全局配置模块 — 使用环境变量注入敏感信息"""
import os
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # ── 应用基础 ──
    APP_NAME: str = "PopStore Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ── 数据库 ──
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./data/popstore.db",
    )

    # ── JWT 认证 ──
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "change-me-in-production-please-use-a-strong-random-string",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8小时

    # ── 管理员 ──
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    LOGIN_MAX_RETRY: int = 5               # 连续失败上限
    LOGIN_LOCK_MINUTES: int = 15            # 锁定时间

    # ── 文件上传 ──
    # 上传根目录：本地直接指向 ./data/uploads；部署到 NAS 时通过环境变量
    # UPLOAD_DIR 指向 NAS 的挂载目录即可（上传会按 年/月/日 自动建子目录归档）。
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    MAX_UPLOAD_SIZE_MB: int = 10
    # 仅作参考说明；真实格式校验在 admin.py 中按文件头（magic number）执行，
    # 仅放行 jpg/jpeg/gif/png/webp。
    ALLOWED_IMAGE_TYPES: List[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    ]

    # ── 爬虫配置 ──
    CRAWLER_SCHEDULE: List[str] = ["02:00", "13:00"]
    CRAWLER_KEYWORDS: List[str] = [
        "快闪店", "二次元快闪", "动漫快闪", "popup store",
        "主题快闪", "限定快闪", "联名快闪", "ACG快闪",
    ]
    CRAWLER_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    # 微信公众号搜索源（搜狗微信已不可用，这里保留配置作为参考）
    CRAWLER_WECHAT_ACCOUNTS: List[str] = []
    CRAWLER_XHS_KEYWORDS: List[str] = ["二次元快闪店", "快闪活动"]
    CRAWLER_WEIBO_TOPICS: List[str] = ["二次元快闪", "快闪店"]

    # ── CORS ──
    CORS_ORIGINS: List[str] = ["*"]

    # ── 接口限流 ──
    RATE_LIMIT: str = "60/minute"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
