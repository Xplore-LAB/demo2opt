from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


Callback = Optional[Callable[..., Any]]


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass
class AgentRuntimeHooks:
    on_log: Callback = None
    on_phase_update: Callback = None
    on_checkpoint: Callback = None
    on_llm_activity: Callback = None
    on_task_progress: Callback = None
    on_monitor_update: Callback = None
    on_result: Callback = None
    on_state_saved: Callback = None
    on_state_cleared: Callback = None

    async def log(self, text: str, level: str = "info", category: str = "system", **kwargs: Any) -> Any:
        if self.on_log is None:
            return None
        return await maybe_await(self.on_log(text=text, level=level, category=category, **kwargs))

    async def phase_update(self, phase: str, status: str, step: Optional[int] = None, **kwargs: Any) -> Any:
        if self.on_phase_update is None:
            return None
        return await maybe_await(self.on_phase_update(phase=phase, status=status, step=step, **kwargs))

    async def checkpoint(self, payload: Dict[str, Any]) -> Any:
        if self.on_checkpoint is None:
            return None
        return await maybe_await(self.on_checkpoint(payload))

    async def llm_activity(self, payload: Dict[str, Any]) -> Any:
        if self.on_llm_activity is None:
            return None
        return await maybe_await(self.on_llm_activity(payload))

    async def task_progress(self, step_name: str, progress: float) -> Any:
        if self.on_task_progress is None:
            return None
        return await maybe_await(self.on_task_progress(step_name=step_name, progress=progress))

    async def monitor_update(
        self,
        semantic_data: List[Dict[str, Any]],
        abnormal_items: List[Dict[str, Any]],
        stage: str,
        **kwargs: Any,
    ) -> Any:
        if self.on_monitor_update is None:
            return None
        return await maybe_await(
            self.on_monitor_update(semantic_data=semantic_data, abnormal_items=abnormal_items, stage=stage, **kwargs)
        )

    async def result(self, payload: Dict[str, Any]) -> Any:
        if self.on_result is None:
            return None
        return await maybe_await(self.on_result(payload))

    async def state_saved(self, task_id: str, path: str, pending_checkpoint: Optional[Dict[str, Any]]) -> Any:
        if self.on_state_saved is None:
            return None
        return await maybe_await(
            self.on_state_saved(task_id=task_id, path=path, pending_checkpoint=pending_checkpoint)
        )

    async def state_cleared(self, task_id: str) -> Any:
        if self.on_state_cleared is None:
            return None
        return await maybe_await(self.on_state_cleared(task_id=task_id))
