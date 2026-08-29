"""全局配置模块 — 使用环境变量注入敏感信息"""
import os
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # ── 应用基础 ──
    APP_NAME: str = "PopStore Platform"
    APP_VERSION: str = "1.0.0"
    # 部署标签：每次有意义的改动请手动 +1（如 2026-08-27-qiniu-admin-v1）。
    # 用于 /api/v1/version 接口与前端 /version.json 比对，确认 NAS 跑的是不是最新代码。
    APP_DEPLOY_TAG: str = "2026-08-27-admin-v2"
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

    # ── 七牛云 KODO 图床 ──
    # AK 可公开配置；SK 必须保密，仅存于服务端环境变量，绝不进代码/前端。
    QINIU_ACCESS_KEY: str = os.getenv("QINIU_ACCESS_KEY", "")
    QINIU_SECRET_KEY: str = os.getenv("QINIU_SECRET_KEY", "")
    QINIU_BUCKET: str = os.getenv("QINIU_BUCKET", "popstore-img")
    # 七牛绑定后的公开访问域名（加速域名），如 https://img.nas.ccxiang.top
    QINIU_PUBLIC_DOMAIN: str = os.getenv("QINIU_PUBLIC_DOMAIN", "https://img.nas.ccxiang.top")
    # 上传域名随存储区域变化：华南-广东=z2 → upload-z2.qiniup.com
    # 华东-浙江=z0 → upload-z0.qiniup.com；华北=z1 → upload-z1.qiniup.com
    QINIU_UPLOAD_DOMAIN: str = os.getenv("QINIU_UPLOAD_DOMAIN", "https://upload-z2.qiniup.com")
    QINIU_REGION: str = os.getenv("QINIU_REGION", "z2")  # z0华东 / z1华北 / z2华南
    QINIU_TOKEN_EXPIRE: int = int(os.getenv("QINIU_TOKEN_EXPIRE", "3600"))  # 秒

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
