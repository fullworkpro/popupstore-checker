"""全局配置模块 — 使用环境变量注入敏感信息"""
import os
from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # ── 应用基础 ──
    APP_NAME: str = "PopStore Platform"
    APP_VERSION: str = "1.2.0"
    # 部署标签：每次有意义的改动请手动 +1（如 2026-08-27-qiniu-admin-v1）。
    # 用于 /api/v1/version 接口与前端 /version.json 比对，确认 NAS 跑的是不是最新代码。
    APP_DEPLOY_TAG: str = "2026-09-03-admin-store-type-filter-v1.4.4"
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
    CRAWLER_ENABLED: bool = True
    CRAWLER_KEYWORDS: List[str] = [
        "快闪店", "二次元快闪", "动漫快闪", "popup store",
        "主题快闪", "限定快闪", "联名快闪", "ACG快闪",
    ]
    # 移动端 UA：m.weibo.cn 是移动接口，用 iPhone UA 比桌面 Chrome 更「像正常访客」，
    # 且参考的 weibo-skill 也明确要求移动端 UA，可降低被拦概率。
    CRAWLER_USER_AGENT: str = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.0 Mobile/15E148 Safari/604.1"
    )
    # 微信公众号搜索源（搜狗微信已不可用，这里保留配置作为参考）
    CRAWLER_WECHAT_ACCOUNTS: List[str] = []
    CRAWLER_XHS_KEYWORDS: List[str] = ["二次元快闪店", "快闪活动"]
    CRAWLER_WEIBO_TOPICS: List[str] = ["二次元快闪", "快闪店"]

    # ── 微博爬虫（m.weibo.cn 移动端 JSON 搜索接口）──
    # 方案：针对「每个二次元 IP 关键词」在全站搜索原创微博，
    # 筛出正文同时含「快闪/快闪店」且命中某一 IP 关键词的原创微博，落入待发布。
    # 不限定单一账号（名创优品只是举例）——要覆盖全站所有品牌/IP 的二次元快闪。
    # 仅当服务器出口 IP 被微博 WAF(SHANHAI) 拦截(HTTP 432) 时，
    # 在「爬虫」页面填写浏览器 Cookie 即可绕过。
    CRAWLER_WEIBO_KEYWORDS: List[str] = [
        # 二次元 / ACG IP（命中其一即视为二次元快闪主题；命中的 IP 名会作为 tag 存入待发布）
        "龙珠", "原神", "鸣潮", "chiikawa", "初音未来", "洛天依",
        "恋与深空", "光与夜之恋", "明日方舟", "崩坏", "碧蓝航线",
        "蛋仔派对", "第五人格", "王者荣耀", "英雄联盟",
        "三丽鸥",
        "蜡笔小新", "哆啦A梦", "名侦探柯南", "宝可梦", "吉卜力",
        "假面骑士", "奥特曼", "LoveLive", "BanG Dream", "偶像梦幻祭",
        "光遇",
    ]
    # 首次运行（无成功记录）时，向前回看的天数；之后用「上次成功时刻」作为 since。
    CRAWLER_WEIBO_LOOKBACK_DAYS: int = 1

    # 微博「账号监控」模式：监控这些官方/品牌账号时间线，抓取原创「快闪」帖。
    # 比全站关键词搜索接口（ok=-100 限流重灾区）稳定得多，游客即可读取时间线。
    # uid 为该账号的数字 ID（打开其主页 URL 中 /u/ 后的数字）；空 uid 表示该账号暂未配置，会被跳过。
    CRAWLER_WEIBO_ACCOUNTS: List[dict] = [
        {"name": "良笑goodsmile", "uid": ""},
        {"name": "名创优品", "uid": "2205447082"},
        {"name": "TOPTOY", "uid": ""},
        {"name": "卡魂", "uid": ""},
        {"name": "aniplex", "uid": ""},
        {"name": "宝可梦pokemon", "uid": ""},
        {"name": "chiikawa吉伊卡哇", "uid": ""},
        {"name": "EnsembleStars旗舰店丨上海", "uid": ""},
        {"name": "谷谷逛谷GuGuGuGu", "uid": ""},
        {"name": "木棉花MUSE", "uid": ""},
    ]
    # 每关键词最多翻几页（每页约 10 条）；用于平衡覆盖度与请求量。
    CRAWLER_WEIBO_MAX_PAGES: int = 3
    # 两种模式各自独立的启停开关（v1.3.1）：
    # 两者可同时开，执行顺序固定为「先 UID 账号监控 → 再全站关键词补充」；
    # UID 是首选（默认开、优先级最高），关键词默认关，仅作为 UID 的补充。
    CRAWLER_WEIBO_UID_ENABLED: bool = True
    CRAWLER_WEIBO_KEYWORD_ENABLED: bool = False
    # 可选：出口 IP 被微博 WAF 拦截时，在浏览器登录后复制 Cookie 填入「爬虫」页面。
    CRAWLER_WEIBO_COOKIE: str = os.getenv("CRAWLER_WEIBO_COOKIE", "")

    # ── 其它平台（规划中，待微博验证通过后再实现爬虫）──
    # 仅作为前端「爬虫」页的占位开关与凭据存储，当前调度器会跳过未实现源。
    CRAWLER_XHS_ENABLED: bool = False
    CRAWLER_XHS_COOKIE: str = os.getenv("CRAWLER_XHS_COOKIE", "")
    CRAWLER_DOUYIN_ENABLED: bool = False
    CRAWLER_DOUYIN_COOKIE: str = os.getenv("CRAWLER_DOUYIN_COOKIE", "")

    # ── CORS ──
    CORS_ORIGINS: List[str] = ["*"]

    # ── 接口限流 ──
    RATE_LIMIT: str = "60/minute"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
