from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.invites import router as invites_router
from app.api.reviews import router as reviews_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.models import AgentRun, Invite, Resume, Tenant, User  # noqa: F401
from app.services.bootstrap import seed_platform_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        await seed_platform_admin(session)
    yield
    await engine.dispose()


app = FastAPI(title="简历审查 Agent", version="1.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(invites_router)
app.include_router(reviews_router)

static_dir = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/report")
async def report_page() -> FileResponse:
    return FileResponse(static_dir / "report.html")


app.mount("/static", StaticFiles(directory=static_dir), name="static")
