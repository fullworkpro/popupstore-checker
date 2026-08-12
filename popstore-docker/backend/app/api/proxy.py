"""图片代理接口。

为什么需要它：
- 管理端 / 小程序在浏览器或客户端里直接加载「外链图片」时，常被目标站点的
  防盗链（Referer 校验）、混合内容（http 图 on https 页）、或微信 downloadFile
  合法域名限制而拦掉，表现为「图不显示但没有任何报错」。
- 本接口在「同源（管理端所在的 nginx / 后端域名）」下把外链图片抓回来再吐给
  前端，绕开上述限制；前端只需把外链 URL 交给它就拿到一张普通同源图片。

安全（SSRF 防护）：
- 仅允许 http / https；
- 解析主机后拒绝内网 / 回环 / 链路本地 / 组播 / 保留地址；
- 仅放行图片 Content-Type；
- 限制体积（10MB）与超时（15s）。

注意：该接口必须公开（<img> 无法携带鉴权头），靠上面的 SSRF 防护兜底。
"""
import ipaddress
import socket
from urllib.parse import unquote, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix="/proxy-image", tags=["proxy"])

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_TIMEOUT = 15.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_ALLOWED_CT_PREFIXES = ("image/",)


def _block_private(host: str) -> None:
    """把主机解析成 IP，拒绝任何内网 / 回环 / 保留地址（SSRF 防护）。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="无法解析的图片地址")
    for info in infos:
        ip = info[4][0].split("%")[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="禁止访问内网地址")


@router.get("")
async def proxy_image(url: str = Query(..., description="待代理的外链图片 URL")):
    raw = unquote(url).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise HTTPException(status_code=400, detail="仅支持 http/https 图片地址")

    # SSRF：先解析主机做内网拦截（DNS 解析后再校验）
    _block_private(parsed.hostname)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            async with client.stream("GET", raw) as resp:
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502, detail=f"上游返回 {resp.status_code}"
                    )
                ct = resp.headers.get("content-type", "")
                if not ct.startswith(_ALLOWED_CT_PREFIXES):
                    raise HTTPException(status_code=400, detail="非图片类型，已拒绝")
                chunks, total = [], 0
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    total += len(chunk)
                    if total > _MAX_BYTES:
                        raise HTTPException(status_code=413, detail="图片过大，已中断")
                    chunks.append(chunk)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="图片获取失败")

    return Response(
        content=b"".join(chunks),
        media_type=ct or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
