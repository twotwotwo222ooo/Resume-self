from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import UserRole
from app.models.invite import Invite
from app.models.tenant import Tenant


def new_invite_token() -> str:
    return token_urlsafe(32)[:48]


async def create_invite(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    email: str,
    role: UserRole,
) -> Invite:
    if role == UserRole.PLATFORM_ADMIN:
        raise ValueError("不能邀请平台管理员")
    invite = Invite(
        tenant_id=tenant_id,
        email=email.lower().strip(),
        role=role.value,
        token=new_invite_token(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.invite_expire_days),
    )
    db.add(invite)
    await db.flush()
    return invite


async def get_tenant_by_id(db: AsyncSession, tenant_id: UUID) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()
