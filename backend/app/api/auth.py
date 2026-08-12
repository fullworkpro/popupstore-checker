"""认证 API"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.models.admin import Admin, LoginAttempt
from app.api.deps import get_current_admin
from app.schemas.schemas import LoginRequest, LoginResponse, MessageResponse

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """管理员登录"""
    client_ip = request.client.host if request.client else "unknown"

    # 查找管理员
    admin = db.query(Admin).filter(Admin.username == req.username).first()

    # 检查账户锁定
    if admin and admin.locked_until and admin.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"账户已被锁定，请 {int((admin.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)} 分钟后重试",
        )

    # 验证密码
    if not admin or not admin.check_password(req.password):
        # 记录失败
        attempt = LoginAttempt(username=req.username, ip_address=client_ip, success=False)
        db.add(attempt)

        # 检查是否需要锁定
        if admin:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            recent_fails = (
                db.query(LoginAttempt)
                .filter(
                    LoginAttempt.username == req.username,
                    LoginAttempt.success == False,
                    LoginAttempt.created_at >= cutoff,
                )
                .count()
            )
            if recent_fails >= settings.LOGIN_MAX_RETRY:
                admin.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)

        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    # 登录成功
    attempt = LoginAttempt(username=req.username, ip_address=client_ip, success=True)
    db.add(attempt)
    db.commit()

    token = create_access_token(data={"sub": admin.id, "username": admin.username})
    return LoginResponse(access_token=token, username=admin.username)


@router.get("/me", response_model=MessageResponse)
def get_me(admin: Admin = Depends(get_current_admin)):
    return MessageResponse(message=f"当前登录: {admin.username}")
