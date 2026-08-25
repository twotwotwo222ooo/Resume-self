from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.resume_review.graph import resume_review_graph

AgentRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

_REGISTRY: dict[str, AgentRunner] = {}


def register(agent_key: str, runner: AgentRunner) -> None:
    _REGISTRY[agent_key] = runner


async def run_agent(agent_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    runner = _REGISTRY.get(agent_key)
    if runner is None:
        raise KeyError(f"未知 Agent：{agent_key}")
    return await runner(payload)


async def _run_resume_review(payload: dict[str, Any]) -> dict[str, Any]:
    return await resume_review_graph.ainvoke(payload)


register("resume_review", _run_resume_review)
