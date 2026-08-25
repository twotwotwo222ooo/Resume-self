from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_platform_admin
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantCreate, TenantOut, TenantPatch
from app.services.invites import create_invite

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/tenants", response_model=TenantOut)
async def create_tenant(
    payload: TenantCreate,
    _: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantOut:
    slug = payload.slug.lower().strip()
    existing = await db.execute(select(Tenant).where(Tenant.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业标识已存在")
    tenant = Tenant(name=payload.name.strip(), slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()
    invite = await create_invite(
        db,
        tenant_id=tenant.id,
        email=str(payload.admin_email),
        role=UserRole.TENANT_ADMIN,
    )
    await db.commit()
    return TenantOut(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        is_active=tenant.is_active,
        invite_token=invite.token,
        invite_email=invite.email,
    )


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(
    _: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TenantOut]:
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()
    return [
        TenantOut(id=str(t.id), name=t.name, slug=t.slug, is_active=t.is_active)
        for t in tenants
    ]


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def patch_tenant(
    tenant_id: str,
    payload: TenantPatch,
    _: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantOut:
    from uuid import UUID

    result = await db.execute(select(Tenant).where(Tenant.id == UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业不存在")
    tenant.is_active = payload.is_active
    await db.commit()
    return TenantOut(id=str(tenant.id), name=tenant.name, slug=tenant.slug, is_active=tenant.is_active)
