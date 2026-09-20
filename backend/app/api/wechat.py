"""公众号草稿箱推送 API（后台「公众号推送」页使用）

推送主逻辑复用已实测跑通的 scripts/push_wechat_draft.py：
    · 图片下载 → 转存微信永久素材（文件名形如 260921_标题_1.jpg，便于素材库按日期辨识）
    · 生成图文正文 → draft/add 建草稿（articles 是数组，支持多图文一次群发，上限 8 篇）

本模块只做三件事：校验凭据、以后台子进程执行脚本、把执行状态落盘供前端轮询。
走子进程而不是同步调用的原因：一次推送要下+传十几张图，动辄 1-3 分钟，
直接同步会把 HTTP 请求拖到 nginx/网关超时；后台执行 + 前端轮询最稳。

凭据文件：backend/data/.wechat_mp（已 gitignore），格式：
    WECHAT_APPID=wx...
    WECHAT_APPSECRET=...
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.models.admin import Admin
from app.models.store import Store, StoreStatus
from app.schemas.schemas import StoreResponse

router = APIRouter(prefix="/admin/wechat", tags=["公众号推送"])

# app/api/wechat.py → parents[0]=api, [1]=app, [2]=backend
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "push_wechat_draft.py"
DATA_DIR = ROOT / "data"
CRED_FILE = DATA_DIR / ".wechat_mp"
PUSHED_FILE = DATA_DIR / ".wechat_pushed.json"
TASK_FILE = DATA_DIR / ".wechat_task.json"
LOG_DIR = DATA_DIR / "outbox"
LOG_FILE = LOG_DIR / "wechat-push.log"

MAX_ARTICLES = 8

_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None
_state: dict = {}


# ── 状态存取 ────────────────────────────────────────────────
def _load_state() -> dict:
    if TASK_FILE.exists():
        try:
            d = json.loads(TASK_FILE.read_text(encoding="utf-8"))
            # 进程已重启但文件里还写着 running → 标记成 stale，避免前端一直转圈
            if d.get("status") == "running":
                d["status"] = "stale"
                d["message"] = "后端重启，上一次任务状态已失效"
            return d
        except Exception:
            pass
    return {"status": "idle", "message": "", "started_at": None,
            "finished_at": None, "returncode": None, "cmd": "", "log": ""}


def _save_state():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TASK_FILE.write_text(json.dumps(_state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_state = _load_state()


def _is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def _tail_log(limit: int = 6000) -> str:
    try:
        if not LOG_FILE.exists():
            return ""
        txt = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        return txt[-limit:]
    except Exception:
        return ""


def public_state() -> dict:
    d = dict(_state)
    if _is_running():
        d["status"] = "running"
        d["log"] = _tail_log()
    return d


# ── 请求模型 ────────────────────────────────────────────────
class PushRequest(BaseModel):
    ids: List[str] = Field(default_factory=list, description="要推送的店铺 id，多篇=多图文一次群发")
    mode: str = Field("single", pattern="^(single|weekly)$")
    light: bool = False          # True=图片走 uploadimg（不占素材库配额，但不可管理）
    url_link: str = ""           # 「阅读原文」链接，可填小程序 URL Link
    days: int = 7                # weekly 模式统计天数
    city: Optional[str] = None   # weekly 模式限定城市
    title: Optional[str] = None  # 自定义标题（单篇时生效）
    force: bool = False          # 忽略已推送记录
    dry_run: bool = False        # 只生成产物不推草稿箱


# ── 凭据 ────────────────────────────────────────────────────
def _read_credentials() -> dict:
    """只读地汇报凭据是否已配置——任何情况下都不回传 AppSecret"""
    info = {"configured": False, "appid": "",
            "miniapp_configured": False, "miniapp_appid": ""}
    if not CRED_FILE.exists():
        return info
    try:
        for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().upper()
            if k == "WECHAT_APPID":
                info["appid"] = v.strip()
            elif k == "WXAPP_APPID":
                info["miniapp_appid"] = v.strip()
    except Exception:
        pass
    info["configured"] = bool(info["appid"]) and not info["appid"].startswith("wx_your")
    info["miniapp_configured"] = bool(info["miniapp_appid"])
    return info


def _load_pushed() -> dict:
    if PUSHED_FILE.exists():
        try:
            return json.loads(PUSHED_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# ── 接口 ────────────────────────────────────────────────────
@router.get("/status")
def status(_: Admin = Depends(get_current_admin)):
    """凭据状态 + 已推送记录 + 当前任务状态"""
    pushed = _load_pushed()
    return {
        "credential": _read_credentials(),
        "pushed": pushed,
        "pushed_count": len(pushed),
        "task": public_state(),
        "script_exists": SCRIPT.exists(),
    }


@router.get("/task")
def task(_: Admin = Depends(get_current_admin)):
    return public_state()


@router.post("/push")
def push(payload: PushRequest, db: Session = Depends(get_db),
         _: Admin = Depends(get_current_admin)):
    global _proc, _state

    cred = _read_credentials()
    if not cred["configured"]:
        raise HTTPException(status_code=400, detail="未配置公众号凭据（backend/data/.wechat_mp）")
    if not SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"推送脚本缺失：{SCRIPT}")

    with _lock:
        if _is_running():
            raise HTTPException(status_code=409, detail="上一次推送还在进行中，请等它跑完")

        # ── 直接从数据库取数，写成 JSON 喂给脚本 ──
        # 这样脚本不必登录后台 API，也就不需要 data/.admin_password，
        # 也不依赖「容器内能否访问到自己的服务地址」。
        if payload.mode == "weekly":
            since = datetime.now() - timedelta(days=payload.days)
            rows = (
                db.query(Store)
                .filter(Store.status == StoreStatus.PUBLISHED.value)
                .filter(Store.created_at >= since)
                .order_by(desc(Store.created_at))
                .all()
            )
        else:
            if not payload.ids:
                raise HTTPException(status_code=400, detail="请至少勾选一篇要推送的快闪店")
            if len(payload.ids) > MAX_ARTICLES:
                raise HTTPException(status_code=400,
                                    detail=f"一次最多 {MAX_ARTICLES} 篇，当前勾选 {len(payload.ids)} 篇")
            rows = (
                db.query(Store)
                .filter(Store.id.in_(payload.ids),
                        Store.status == StoreStatus.PUBLISHED.value)
                .all()
            )
            found = {r.id for r in rows}
            missing = [i for i in payload.ids if i not in found]
            if missing:
                print(f"[警告] 这些 id 不是已发布状态：{missing}")

        if not rows:
            raise HTTPException(status_code=400, detail="没有符合条件的已发布快闪店")

        stores = [StoreResponse.model_validate(r).model_dump(mode="json") for r in rows]

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        input_path = LOG_DIR / "wechat-push-input.json"
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(stores, f, ensure_ascii=False)

        args: List[str] = ["--input-json", str(input_path)]
        if payload.mode == "weekly":
            args += ["--weekly", "--days", str(payload.days)]
            if payload.city:
                args += ["--city", payload.city]
        else:
            pass  # 单篇：数据已由 --input-json 喂入，无需再传 ids
        if payload.title:
            args += ["--title", payload.title]
        if payload.url_link:
            args += ["--url-link", payload.url_link]
        if payload.light:
            args.append("--light")
        if payload.force:
            args.append("--force")
        if payload.dry_run:
            args.append("--dry-run")

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(SCRIPT)] + args
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        logf = open(LOG_FILE, "w", encoding="utf-8")
        try:
            _proc = subprocess.Popen(
                cmd, cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT,
                env=env, text=True, encoding="utf-8", errors="replace",
            )
        except Exception as e:
            logf.close()
            raise HTTPException(status_code=500, detail=f"启动推送失败：{e}")

        _state = {
            "status": "running",
            "message": "dry-run：只生成产物，不建草稿" if payload.dry_run else "正在转存图片并创建草稿…",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "returncode": None,
            "cmd": " ".join(cmd[1:]),
            "log": "",
        }
        _save_state()

        def _watch(proc: subprocess.Popen, fh, dry: bool):
            global _state
            rc = proc.wait()
            try:
                fh.close()
            except Exception:
                pass
            with _lock:
                log = _tail_log()
                ok = rc == 0
                if not ok:
                    msg = f"推送失败（退出码 {rc}），请看日志"
                elif dry:
                    msg = "dry-run 完成，产物在 data/outbox/，未建草稿"
                else:
                    msg = "草稿已创建，去公众号后台草稿箱核对"
                _state = {
                    **_state,
                    "status": "success" if ok else "error",
                    "message": msg,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "returncode": rc,
                    "log": log,
                }
                _save_state()

        threading.Thread(target=_watch, args=(_proc, logf, payload.dry_run), daemon=True).start()

    return {"started": True, "task": public_state()}
