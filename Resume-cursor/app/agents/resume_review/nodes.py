from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from openai import AuthenticationError, BadRequestError, PermissionDeniedError
from pydantic import ValidationError

from app.agents.resume_review.prompts import EXTRACT_PROMPT, SYSTEM_PROMPT, build_extract_prompt, build_user_prompt
from app.agents.resume_review.schemas import (
    LLMReport,
    ResumeExtract,
    SCORE_WEIGHTS,
    clamp_score,
    weighted_overall,
)
from app.core.config import settings
from app.services.pdf_extract import extract_anchored_text


class ReviewState(TypedDict, total=False):
    pdf_bytes: bytes
    job_title: str | None
    job_description: str | None
    anchored_text: str
    structured_resume: dict[str, Any]
    llm_report: dict[str, Any]
    overall_score: int
    weights: dict[str, float]


def _build_llm() -> ChatOpenAI:
    if not settings.deepseek_api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.2,
        extra_body={"thinking": {"type": "disabled"}},
    )


def _structured_llm(llm: ChatOpenAI, schema: type, method: str):
    return llm.with_structured_output(schema, method=method)


def _dump_model(model: Any, schema: type) -> dict[str, Any]:
    if model is None:
        raise ValueError(f"{schema.__name__} 为空，模型未返回结构化结果")
    if isinstance(model, schema):
        return model.model_dump()
    if isinstance(model, dict) and "parsed" in model:
        parsed = model.get("parsed")
        if parsed is None:
            raise ValueError(f"{schema.__name__} 为空，模型未返回结构化结果")
        model = parsed
        if isinstance(model, schema):
            return model.model_dump()
    return schema.model_validate(model).model_dump()


def _is_retryable_schema_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    markers = (
        "tool_choice",
        "json_schema",
        "response_format",
        "invalid_request_error",
        "thinking mode",
    )
    if any(marker in text for marker in markers):
        return True
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, (BadRequestError, NotImplementedError)):
            return True
        current = current.__cause__ or current.__context__
    return False


async def _ainvoke_structured(llm: ChatOpenAI, schema: type, messages: list[Any]) -> Any:
    last_error: BaseException | None = None
    for method in ("json_mode", "json_schema", "function_calling"):
        try:
            result = await _structured_llm(llm, schema, method).ainvoke(messages)
            if result is None:
                last_error = ValueError(f"{method} 返回空结果")
                continue
            if isinstance(result, dict) and result.get("parsed") is None and "raw" in result:
                last_error = ValueError(f"{method} 未能解析结构化结果")
                continue
            return result
        except (AuthenticationError, PermissionDeniedError):
            raise
        except Exception as exc:
            last_error = exc
    raise RuntimeError("模型未能按 schema 输出结构化结果") from last_error


async def extract_pdf(state: ReviewState) -> dict[str, Any]:
    anchored = await asyncio.to_thread(extract_anchored_text, state["pdf_bytes"])
    return {"anchored_text": anchored}


async def extract_structure(state: ReviewState) -> dict[str, Any]:
    llm = _build_llm()
    messages = [
        SystemMessage(content=EXTRACT_PROMPT),
        HumanMessage(content=build_extract_prompt(state["anchored_text"])),
    ]
    try:
        extracted = await _ainvoke_structured(llm, ResumeExtract, messages)
        return {"structured_resume": _dump_model(extracted, ResumeExtract)}
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise RuntimeError(
            "DeepSeek API Key 无效或无权限。请到 https://platform.deepseek.com/api_keys "
            "创建密钥，写入项目根目录 .env 的 DEEPSEEK_API_KEY，然后重启服务。"
        ) from exc
    except Exception:
        return {"structured_resume": ResumeExtract().model_dump()}


async def review_llm(state: ReviewState) -> dict[str, Any]:
    llm = _build_llm()
    prompt = build_user_prompt(
        anchored_text=state["anchored_text"],
        job_title=state.get("job_title"),
        job_description=state.get("job_description"),
        structured_resume=state.get("structured_resume"),
    )
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    try:
        report = await _ainvoke_structured(llm, LLMReport, messages)
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise RuntimeError(
            "DeepSeek API Key 无效或无权限。请到 https://platform.deepseek.com/api_keys "
            "创建密钥，写入项目根目录 .env 的 DEEPSEEK_API_KEY，然后重启服务。"
        ) from exc
    return {"llm_report": _dump_model(report, LLMReport)}


def _keep_real_anchors(evidence: list[str], anchored_text: str) -> list[str]:
    valid: list[str] = []
    seen: set[str] = set()
    for raw in evidence:
        anchor = (raw or "").strip().strip("[]")
        if not anchor or anchor in seen:
            continue
        if f"[{anchor}]" not in anchored_text:
            continue
        seen.add(anchor)
        valid.append(anchor)
    return valid


async def validate_and_score(state: ReviewState) -> dict[str, Any]:
    try:
        report = LLMReport.model_validate(state["llm_report"])
    except ValidationError as exc:
        raise ValueError(f"模型输出不符合报告结构：{exc}") from exc

    anchored_text = state.get("anchored_text") or ""
    scores = report.scores
    missing: list[str] = []
    for name in scores.model_fields:
        dim = getattr(scores, name)
        dim.score = clamp_score(dim.score)
        dim.evidence = _keep_real_anchors(dim.evidence, anchored_text)
        if not dim.evidence:
            missing.append(name)
    if missing:
        raise ValueError(f"以下维度未引用有效简历锚点：{', '.join(missing)}")
    report.summary.job_fit.score = clamp_score(report.summary.job_fit.score)
    if not (state.get("job_description") or "").strip():
        scores.tech_match.score = min(scores.tech_match.score, 69)
        report.summary.job_fit.score = min(report.summary.job_fit.score, 69)
    overall = weighted_overall(scores)
    return {
        "llm_report": report.model_dump(),
        "overall_score": overall,
        "weights": SCORE_WEIGHTS,
    }


def build_resume_review_graph(checkpointer: Any | None = None):
    graph = StateGraph(ReviewState)
    graph.add_node("extract_pdf", extract_pdf)
    graph.add_node("extract_structure", extract_structure)
    graph.add_node("review_llm", review_llm)
    graph.add_node("validate_and_score", validate_and_score)
    graph.add_edge(START, "extract_pdf")
    graph.add_edge("extract_pdf", "extract_structure")
    graph.add_edge("extract_structure", "review_llm")
    graph.add_edge("review_llm", "validate_and_score")
    graph.add_edge("validate_and_score", END)
    if checkpointer is None:
        return graph.compile()
    return graph.compile(checkpointer=checkpointer)
