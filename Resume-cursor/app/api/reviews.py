import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import run_agent
from app.core.config import settings
from app.core.deps import require_tenant_user
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus, UserRole
from app.models.resume import Resume
from app.models.user import User
from app.schemas.review import (
    ExtractPreviewResponse,
    ReviewCreateResponse,
    ReviewDeleteResponse,
    ReviewIdsRequest,
    ReviewListItem,
)
from app.services.pdf_extract import PdfExtractError, extract_resume

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

RESUME_REVIEW_KEY = "resume_review"


def _upload_path(tenant_id: UUID, user_id: UUID, stored_name: str) -> Path:
    directory = Path(settings.upload_dir) / str(tenant_id) / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / stored_name


def _overall_from_output(output: dict | None) -> int | None:
    if not output:
        return None
    value = output.get("overall_score")
    return int(value) if value is not None else None


async def _read_pdf_bytes(file: UploadFile) -> tuple[str, bytes]:
    filename = file.filename or "resume.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 PDF 文件")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")
    if len(pdf_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件超过 8MB 上限")
    return filename, pdf_bytes


@router.post("/extract", response_model=ExtractPreviewResponse)
async def preview_extract(
    file: UploadFile = File(...),
    _: User = Depends(require_tenant_user),
) -> ExtractPreviewResponse:
    filename, pdf_bytes = await _read_pdf_bytes(file)
    try:
        extracted = await asyncio.to_thread(extract_resume, pdf_bytes)
    except PdfExtractError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ExtractPreviewResponse(
        filename=filename,
        anchored_text=extracted.anchored_text,
        char_count=len(extracted.anchored_text),
        sentence_count=extracted.sentence_count,
        section_count=extracted.section_count,
        fallback_sentence_count=extracted.fallback_sentence_count,
        fallback_ratio=extracted.fallback_ratio,
        layout=extracted.layout,
        page_count=extracted.page_count,
    )


@router.post("", response_model=ReviewCreateResponse)
async def create_review(
    file: UploadFile = File(...),
    job_title: str | None = Form(default=None),
    job_description: str | None = Form(default=None),
    user: User = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewCreateResponse:
    filename, pdf_bytes = await _read_pdf_bytes(file)

    stored_name = f"{uuid4().hex}.pdf"
    dest = await asyncio.to_thread(_upload_path, user.tenant_id, user.id, stored_name)
    async with aiofiles.open(dest, "wb") as handle:
        await handle.write(pdf_bytes)

    resume = Resume(
        tenant_id=user.tenant_id,
        user_id=user.id,
        filename=filename,
        extracted_text="",
        source_path=str(dest),
    )
    db.add(resume)
    await db.flush()

    run = AgentRun(
        tenant_id=user.tenant_id,
        user_id=user.id,
        agent_key=RESUME_REVIEW_KEY,
        resume_id=resume.id,
        status=AgentRunStatus.RUNNING.value,
        input_json={
            "job_title": (job_title or "").strip() or None,
            "job_description": (job_description or "").strip() or None,
            "filename": filename,
        },
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await db.refresh(resume)

    try:
        result = await run_agent(
            RESUME_REVIEW_KEY,
            {
                "pdf_bytes": pdf_bytes,
                "job_title": (job_title or "").strip() or None,
                "job_description": (job_description or "").strip() or None,
            },
        )
        resume.extracted_text = result.get("anchored_text") or ""
        run.status = AgentRunStatus.SUCCEEDED.value
        run.output_json = {
            "overall_score": result.get("overall_score"),
            "weights": result.get("weights"),
            "report": result.get("llm_report"),
        }
        run.error = None
    except PdfExtractError as exc:
        run.status = AgentRunStatus.FAILED.value
        run.error = str(exc)
    except Exception as exc:
        run.status = AgentRunStatus.FAILED.value
        run.error = str(exc)

    await db.commit()
    await db.refresh(run)

    output = run.output_json or {}
    if run.status != AgentRunStatus.SUCCEEDED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=run.error or "审查失败",
        )
    return ReviewCreateResponse(
        id=str(run.id),
        agent_key=run.agent_key,
        status=run.status,
        overall_score=_overall_from_output(output),
        weights=output.get("weights"),
        report=output.get("report"),
        filename=filename,
        created_at=run.created_at,
        error=run.error,
    )


def _scoped_runs(user: User):
    query = select(AgentRun).where(
        AgentRun.tenant_id == user.tenant_id,
        AgentRun.agent_key == RESUME_REVIEW_KEY,
    )
    if user.role == UserRole.MEMBER.value:
        query = query.where(AgentRun.user_id == user.id)
    return query


def _parse_review_ids(raw_ids: list[str]) -> list[UUID]:
    parsed: list[UUID] = []
    seen: set[UUID] = set()
    for raw in raw_ids:
        try:
            run_id = UUID(raw)
        except (TypeError, ValueError):
            continue
        if run_id in seen:
            continue
        seen.add(run_id)
        parsed.append(run_id)
    return parsed


async def _delete_review_runs(user: User, db: AsyncSession, run_ids: list[UUID]) -> int:
    if not run_ids:
        return 0
    result = await db.execute(_scoped_runs(user).where(AgentRun.id.in_(run_ids)))
    runs = list(result.scalars().all())
    resume_ids = {run.resume_id for run in runs if run.resume_id}
    paths: list[Path] = []
    for run in runs:
        await db.delete(run)
    await db.flush()
    for resume_id in resume_ids:
        leftover = await db.execute(select(AgentRun.id).where(AgentRun.resume_id == resume_id).limit(1))
        if leftover.scalar_one_or_none() is not None:
            continue
        resume = await db.get(Resume, resume_id)
        if resume is None or resume.tenant_id != user.tenant_id:
            continue
        if resume.source_path:
            paths.append(Path(resume.source_path))
        await db.delete(resume)
    await db.commit()
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return len(runs)


@router.get("", response_model=list[ReviewListItem])
async def list_reviews(
    user: User = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewListItem]:
    result = await db.execute(_scoped_runs(user).order_by(AgentRun.created_at.desc()))
    runs = result.scalars().all()
    items: list[ReviewListItem] = []
    for run in runs:
        output = run.output_json or {}
        items.append(
            ReviewListItem(
                id=str(run.id),
                status=run.status,
                overall_score=_overall_from_output(output),
                filename=(run.input_json or {}).get("filename"),
                job_title=(run.input_json or {}).get("job_title"),
                created_at=run.created_at,
            )
        )
    return items


@router.post("/batch-delete", response_model=ReviewDeleteResponse)
async def batch_delete_reviews(
    payload: ReviewIdsRequest,
    user: User = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewDeleteResponse:
    run_ids = _parse_review_ids(payload.ids)
    if not run_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要删除的记录")
    deleted = await _delete_review_runs(user, db, run_ids)
    return ReviewDeleteResponse(deleted=deleted)


@router.delete("/{review_id}", response_model=ReviewDeleteResponse)
async def delete_review(
    review_id: str,
    user: User = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewDeleteResponse:
    run_ids = _parse_review_ids([review_id])
    if not run_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    deleted = await _delete_review_runs(user, db, run_ids)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    return ReviewDeleteResponse(deleted=deleted)


@router.get("/{review_id}", response_model=ReviewCreateResponse)
async def get_review(
    review_id: str,
    user: User = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewCreateResponse:
    try:
        run_uuid = UUID(review_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    result = await db.execute(_scoped_runs(user).where(AgentRun.id == run_uuid))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    output = run.output_json or {}
    return ReviewCreateResponse(
        id=str(run.id),
        agent_key=run.agent_key,
        status=run.status,
        overall_score=_overall_from_output(output),
        weights=output.get("weights"),
        report=output.get("report"),
        filename=(run.input_json or {}).get("filename"),
        created_at=run.created_at,
        error=run.error,
    )
