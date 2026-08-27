"""七牛云 KODO 图床 — 上传凭证（uptoken）签发 + 服务端代理上传

安全模型：
- SecretKey 仅存于后端环境变量，绝不下发前端。
- 小程序：调用 /qiniu/uptoken 拿有时效 uptoken 后直传七牛，不经过业务服务器。
- 管理后台：调用 /qiniu/upload 由服务端用 SDK 直传七牛（SK 不落地前端），
  返回公网 URL，前端无需改造即可拿到与本地上传一致的 {url} 结构。
- 上传 key 由服务端生成（uuid），避免覆盖/遍历；并限制为图片 MIME 与大小。
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from qiniu import Auth, put_data
from app.core.config import settings
from app.api.deps import get_current_admin
from app.models.admin import Admin

router = APIRouter(prefix="/qiniu", tags=["图床"])


def _build_auth() -> Auth:
    if not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
        raise HTTPException(status_code=500, detail="七牛云未配置（缺少 AK 或 SK）")
    return Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)


# 允许的图片文件头（magic number）签名 → 扩展名
_IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",            # JPEG / JPG
    b"\x89PNG\r\n\x1a\n": ".png",       # PNG
    b"GIF87a": ".gif",                  # GIF87a
    b"GIF89a": ".gif",                  # GIF89a
    # WEBP 为 RIFF 容器，需二次校验偏移 8 处的 "WEBP" 标记，单独处理
}


def _ext_from_content(content: bytes) -> Optional[str]:
    """通过文件头识别真实图片类型，返回扩展名或 None（不信任客户端声明）。"""
    if len(content) < 12:
        return None
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    for sig, ext in _IMAGE_SIGNATURES.items():
        if content[: len(sig)] == sig:
            return ext
    return None


@router.get("/uptoken", response_model=dict)
def get_upload_token(
    prefix: str = Query("stores", description="对象 key 的目录前缀，用于隔离不同业务"),
    ext: str = Query("jpg", description="文件扩展名（不含点），用于拼装 key"),
    _: Admin = Depends(get_current_admin),
):
    """签发七牛上传凭证（upload token）。

    返回 uptoken + 服务端生成的 key + 七牛上传域名 + 拼接好的公网 URL。
    前端拿到后用 wx.uploadFile / 表单直传七牛，上传成功后直接使用返回的 public_url。
    """
    auth = _build_auth()

    ext = (ext or "jpg").strip().lstrip(".").lower()
    key = f"{prefix.strip('/')}/{uuid.uuid4().hex}.{ext}"

    # 上传策略：仅允许图片 MIME、单文件上限 20MB；token 即便泄露也难以上传非图片/超大文件
    policy = {
        "mimeLimit": "image/*",
        "fsizeLimit": 20 * 1024 * 1024,
    }
    token = auth.upload_token(
        settings.QINIU_BUCKET, key, expires=settings.QINIU_TOKEN_EXPIRE, policy=policy
    )

    public_url = settings.QINIU_PUBLIC_DOMAIN.rstrip("/") + "/" + key
    return {
        "uptoken": token,
        "key": key,
        "upload_domain": settings.QINIU_UPLOAD_DOMAIN,
        "public_url": public_url,
        "expires_in": settings.QINIU_TOKEN_EXPIRE,
    }


@router.post("/upload", response_model=dict)
async def upload_to_qiniu(
    file: UploadFile = File(...),
    _: Admin = Depends(get_current_admin),
):
    """管理后台代理上传：后端用七牛 SDK 直传 bucket，返回公网 URL。

    与小程序直传共用七牛存储；返回 {url, key} 与旧本地上传接口结构一致，
    前端 uploadImage() 仅改请求路径即可，无需改动取结果逻辑。
    """
    content = await file.read()

    # 1) 文件头校验（不信任客户端声明的类型/后缀）
    ext = _ext_from_content(content)
    if ext is None:
        raise HTTPException(status_code=400, detail="仅支持 JPG/JPEG/PNG/GIF/WEBP 图片")

    # 2) 大小校验（与 uptoken 策略一致：20MB）
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 20MB")

    # 3) 服务端生成 uuid key，避免覆盖/遍历
    key = f"stores/{uuid.uuid4().hex}{ext}"

    # 4) 用七牛 SDK 直传（SK 仅存在于服务端，不会下发前端）
    auth = _build_auth()
    token = auth.upload_token(
        settings.QINIU_BUCKET, key, expires=settings.QINIU_TOKEN_EXPIRE
    )
    ret, info = put_data(token, key, content)
    if info.status_code != 200:
        raise HTTPException(status_code=500, detail=f"七牛上传失败：{info.text_body}")

    # 5) 返回公网 URL（与本地上传返回 {url} 结构一致，前端无需改取结果逻辑）
    url = settings.QINIU_PUBLIC_DOMAIN.rstrip("/") + "/" + key
    return {"url": url, "key": key}
