"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.database import init_db
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.mini import router as mini_router
from app.api.proxy import router as proxy_router
from app.api.qiniu import router as qiniu_router
from app.api.version import router as version_router, build_version_payload
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("popstore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库"""
    logger.info("🚀 PopStore Platform 启动中...")
    init_db()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    logger.info("✅ 数据库初始化完成")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 静态文件（上传图片）
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

# 路由注册
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(mini_router, prefix="/api/v1")
app.include_router(proxy_router, prefix="/api/v1")
app.include_router(qiniu_router, prefix="/api/v1")
app.include_router(version_router, prefix="/api/v1")


@app.get("/version.json", response_model=dict)
def version_json():
    """根路径部署指纹：popstore.nas.ccxiang.top/version.json 直接返回后端部署标签，
    与 /api/v1/version 同源，便于在默认域名一键核对。"""
    return build_version_payload({"source": "backend"})


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    # 顺带探一下数据库连通性：若 DB 在 NAS 网络卷上锁死，这里会直接暴露
    db_status = "ok"
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        db_status = f"db_error: {e}"
    return {"status": "ok", "db": db_status}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 参数校验失败时，把具体失败字段 + 收到的请求体打到日志，便于排障。

    注意：不要用 BaseHTTPMiddleware 在全局提前读 body。它会让 POST 请求在
    Starlette 下挂起（GET 正常、POST 超时），表现就是登录 30s 超时且后端无访问日志。
    这里在 422 处理函数内直接 await request.body() 即可（FastAPI 已缓存请求体）。
    """
    try:
        raw = await request.body()
        body_str = raw.decode("utf-8", "replace") if raw else "<空请求体>"
    except Exception:
        body_str = "<无法读取请求体>"
    logger.error("❌ 422 参数校验失败 | %s %s", request.method, request.url.path)
    logger.error("   收到的请求体: %s", body_str[:3000])
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []))
        logger.error(
            "   字段[%s] -> %s (type=%s, input=%r)",
            loc,
            e.get("msg"),
            e.get("type"),
            e.get("input"),
        )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
