import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


async def seed_platform_admin(db: AsyncSession) -> None:
    email = settings.platform_admin_email.lower().strip()
    result = await db.execute(
        select(User).where(User.email == email, User.role == UserRole.PLATFORM_ADMIN.value)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return
    password_hash = await asyncio.to_thread(hash_password, settings.platform_admin_password)
    admin = User(
        tenant_id=None,
        email=email,
        password_hash=password_hash,
        role=UserRole.PLATFORM_ADMIN.value,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
