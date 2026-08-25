from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_tenant_admin
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.invite import Invite
from app.models.user import User
from app.schemas.invite import InviteCreate, InviteOut
from app.services.invites import create_invite

router = APIRouter(prefix="/api/invites", tags=["invites"])


@router.post("", response_model=InviteOut)
async def create_tenant_invite(
    payload: InviteCreate,
    user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> InviteOut:
    if payload.role not in {UserRole.TENANT_ADMIN, UserRole.MEMBER}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能邀请企业管理员或成员")
    invite = await create_invite(
        db,
        tenant_id=user.tenant_id,
        email=str(payload.email),
        role=payload.role,
    )
    await db.commit()
    await db.refresh(invite)
    return InviteOut(
        id=str(invite.id),
        email=invite.email,
        role=UserRole(invite.role),
        token=invite.token,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
    )


@router.get("", response_model=list[InviteOut])
async def list_invites(
    user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> list[InviteOut]:
    result = await db.execute(
        select(Invite)
        .where(Invite.tenant_id == user.tenant_id)
        .order_by(Invite.created_at.desc())
    )
    invites = result.scalars().all()
    return [
        InviteOut(
            id=str(item.id),
            email=item.email,
            role=UserRole(item.role),
            token=item.token,
            expires_at=item.expires_at,
            used_at=item.used_at,
        )
        for item in invites
    ]
