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


# 提前读取并缓存请求体，供 422 异常处理器打印（否则校验消费后无法再读）
@app.middleware("http")
async def _capture_request_body(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            request.state.raw_body = await request.body()
        except Exception:
            request.state.raw_body = b""
    else:
        request.state.raw_body = b""
    response = await call_next(request)
    return response


# 静态文件（上传图片）
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

# 路由注册
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(mini_router, prefix="/api/v1")
app.include_router(proxy_router, prefix="/api/v1")


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
    """422 参数校验失败时，把具体失败字段 + 收到的请求体打到日志，便于排障。"""
    raw = getattr(request.state, "raw_body", b"")
    body_str = raw.decode("utf-8", "replace") if raw else "<空请求体>"
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
