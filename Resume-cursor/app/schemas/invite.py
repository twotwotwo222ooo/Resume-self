from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class InviteCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.MEMBER


class InviteOut(BaseModel):
    id: str
    email: str
    role: UserRole
    token: str
    expires_at: datetime
    used_at: datetime | None
