from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items() if k != "service_overrides"}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


class GraphStateStore:
    def __init__(self, root_dir: Optional[str] = None):
        base_dir = Path(root_dir) if root_dir else Path(__file__).resolve().parents[3] / "task_progress" / "graph_runs"
        self.root_dir = base_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.root_dir / f"{task_id}.json"

    def save_snapshot(self, task_id: str, state: Dict[str, Any]) -> str:
        path = self._path(task_id)
        payload = {
            "schema_version": 1,
            "task_id": task_id,
            "saved_at": datetime.now().isoformat(),
            "current_node": state.get("current_node"),
            "next_node": state.get("next_node"),
            "resume_node": state.get("resume_node"),
            "pending_checkpoint": _to_jsonable(state.get("pending_checkpoint")),
            "state": _to_jsonable(state),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def load_snapshot(self, task_id: str) -> Dict[str, Any]:
        path = self._path(task_id)
        if not path.exists():
            raise FileNotFoundError(f"Graph state snapshot not found for task_id={task_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def clear_snapshot(self, task_id: str) -> None:
        path = self._path(task_id)
        if path.exists():
            path.unlink()

