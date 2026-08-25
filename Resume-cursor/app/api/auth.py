import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.invite import Invite
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    users = list(result.scalars().all())
    if not users:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    user = users[0]
    if len(users) > 1:
        matched = None
        for candidate in users:
            ok = await asyncio.to_thread(verify_password, payload.password, candidate.password_hash)
            if ok and candidate.is_active:
                matched = candidate
                break
        if matched is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
        user = matched
    else:
        ok = await asyncio.to_thread(verify_password, payload.password, user.password_hash)
        if not ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已停用")
    if user.tenant_id is not None:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None or not tenant.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="企业不存在或已停用")
    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    from datetime import datetime, timezone

    result = await db.execute(select(Invite).where(Invite.token == payload.token.strip()))
    invite = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if invite is None or invite.used_at is not None or invite.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码无效或已过期")
    email = payload.email.lower().strip()
    if email != invite.email.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱与邀请不一致")

    tenant_result = await db.execute(select(Tenant).where(Tenant.id == invite.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业不存在或已停用")

    existing = await db.execute(
        select(User).where(User.tenant_id == invite.tenant_id, User.email == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已在本企业注册")

    password_hash = await asyncio.to_thread(hash_password, payload.password)
    user = User(
        tenant_id=invite.tenant_id,
        email=email,
        password_hash=password_hash,
        role=invite.role,
        is_active=True,
    )
    invite.used_at = now
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserOut:
    tenant_name = None
    if user.tenant_id is not None:
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        tenant_name = tenant.name if tenant else None
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=UserRole(user.role),
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        tenant_name=tenant_name,
    )
