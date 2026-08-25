from pydantic import BaseModel, EmailStr, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_-]+$")
    admin_email: EmailStr


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    invite_token: str | None = None
    invite_email: str | None = None


class TenantPatch(BaseModel):
    is_active: bool
