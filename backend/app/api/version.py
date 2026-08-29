"""部署指纹接口 — 一条命令确认 NAS 上跑的是不是最新代码。

返回字段：
- app_version        应用版本号（config.APP_VERSION）
- deploy_tag         人工可读的部署标签（config.APP_DEPLOY_TAG），每次有意义改动手动 +1
- backend_fingerprint 对"部署关键文件"内容做 sha256；文件内容一旦变化，指纹必变。
                     可与本地同法计算的值比对，确认「容器代码 == 本地代码」。
- fingerprint_files  参与指纹计算的相对文件路径（相对 backend/app 目录），便于核对范围

用法（在 NAS 上）：
    curl -s https://popstore.nas.ccxiang.top/api/v1/version
本地对照（可选）：
    python - <<'PY'
    import hashlib, os
    app_dir = "backend/app"   # 改为你本地实际路径
    files = ["main.py", "api/qiniu.py", "api/admin.py"]
    h = hashlib.sha256()
    for rel in files:
        p = os.path.join(app_dir, rel)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h.update(rel.encode()); h.update(f.read())
    print(h.hexdigest())
    PY
若两者 fingerprint 一致 → 容器跑的就是这份代码；不一致 → NAS 副本未同步（旧）。
"""
import hashlib
import os

from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/version", tags=["部署"])

# 本文件位于 backend/app/api/version.py → 上级目录即 backend/app
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 参与指纹计算的"部署关键文件"（相对 backend/app 目录）。
# 这些文件的改动直接影响线上行为，故纳入指纹；其余文件变化不改变指纹。
_FINGERPRINT_FILES = [
    "main.py",
    "api/qiniu.py",
    "api/admin.py",
]


def _compute_fingerprint() -> str:
    h = hashlib.sha256()
    for rel in _FINGERPRINT_FILES:
        path = os.path.join(_APP_DIR, rel)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                h.update(rel.encode("utf-8"))
                h.update(f.read())
    return h.hexdigest()


# 在模块导入（应用启动）时计算一次，避免每次请求重复读文件
_BACKEND_FINGERPRINT = _compute_fingerprint()


def build_version_payload(extra=None):
    """构造部署指纹响应体；extra 可附加额外字段（如 source 标识）。"""
    payload = {
        "app_version": settings.APP_VERSION,
        "deploy_tag": getattr(settings, "APP_DEPLOY_TAG", "unknown"),
        "backend_fingerprint": _BACKEND_FINGERPRINT,
        "fingerprint_files": _FINGERPRINT_FILES,
    }
    if extra:
        payload.update(extra)
    return payload


@router.get("", response_model=dict)
@router.get("/", response_model=dict)
def get_version():
    return build_version_payload()
