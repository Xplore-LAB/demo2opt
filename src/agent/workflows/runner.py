from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from src.agent.core.config import load_agent_config
from src.agent.core.persistence import GraphStateStore
from src.agent.core.runtime import AgentRuntimeHooks
from src.agent.core.state import OptimizationState
from src.agent.workflows.graph import build_optimization_graph


def build_initial_state(inputs: Optional[Dict[str, Any]] = None) -> OptimizationState:
    inputs = inputs or {}
    config = load_agent_config(inputs)
    task_id = str(inputs.get("task_id") or uuid.uuid4())
    return OptimizationState(
        task_id=task_id,
        session_id=str(inputs.get("session_id") or f"session-{task_id}"),
        created_at=datetime.now().isoformat(),
        entrypoint=config.entrypoint,
        data_file=config.data_file,
        file_name=str(inputs.get("file_name") or ""),
        display_file_name=str(inputs.get("display_file_name") or ""),
        data_source=config.data_source,
        task_note=config.task_note,
        enable_async=config.enable_async,
        enable_cot=config.enable_cot,
        use_asu_pipeline=config.use_asu_pipeline,
        auto_confirm=config.auto_confirm,
        llm_config=config.llm_config or {},
        dify_config=config.dify_config or {},
        execution_feedback=config.execution_feedback or {},
        enable_closed_loop_validation=config.enable_closed_loop_validation,
        service_overrides=dict(inputs.get("service_overrides") or {}),
        human_decisions=dict(inputs.get("human_decisions") or {}),
        interaction_records=[],
        llm_activity_history=[],
        execution_history=[],
        status="pending",
        cancelled=False,
        cancel_message="",
        current_node="",
        next_node="bootstrap_run",
        resume_node="",
    )


async def arun_analysis(inputs: Optional[Dict[str, Any]] = None, hooks: Optional[AgentRuntimeHooks] = None) -> Dict[str, Any]:
    hooks = hooks or AgentRuntimeHooks()
    store = GraphStateStore()
    graph = build_optimization_graph(hooks, store)
    final_state = await graph.ainvoke(build_initial_state(inputs))
    if final_state.get("pending_checkpoint"):
        return final_state
    if final_state.get("task_id"):
        store.clear_snapshot(final_state["task_id"])
        await hooks.state_cleared(final_state["task_id"])
    return final_state


def run_analysis(inputs: Optional[Dict[str, Any]] = None, hooks: Optional[AgentRuntimeHooks] = None) -> Dict[str, Any]:
    return asyncio.run(arun_analysis(inputs, hooks))


async def aresume_analysis(task_id: str, decision: str, hooks: Optional[AgentRuntimeHooks] = None) -> Dict[str, Any]:
    hooks = hooks or AgentRuntimeHooks()
    store = GraphStateStore()
    payload = store.load_snapshot(task_id)
    state = dict(payload.get("state") or {})
    checkpoint = dict(state.get("pending_checkpoint") or {})
    if checkpoint:
        human_decisions = dict(state.get("human_decisions") or {})
        human_decisions[checkpoint.get("checkpoint_key")] = decision
        state["human_decisions"] = human_decisions
    state["resume_node"] = state.get("resume_node") or checkpoint.get("resume_node") or state.get("current_node")
    state["pending_checkpoint"] = None
    state["service_overrides"] = {}
    graph = build_optimization_graph(hooks, store)
    final_state = await graph.ainvoke(state)
    if not final_state.get("pending_checkpoint"):
        store.clear_snapshot(task_id)
        await hooks.state_cleared(task_id)
    return final_state


def resume_analysis(task_id: str, decision: str, hooks: Optional[AgentRuntimeHooks] = None) -> Dict[str, Any]:
    return asyncio.run(aresume_analysis(task_id, decision, hooks))

