import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskProgress:
    task_id: str
    status: str
    progress: float
    current_step: str
    total_steps: int
    current_step_index: int
    start_time: str
    end_time: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None


class TaskManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self.tasks: Dict[str, TaskProgress] = {}
        self._storage_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "task_progress",
        )
        os.makedirs(self._storage_dir, exist_ok=True)
        self.load_tasks_from_disk()

    def load_tasks_from_disk(self):
        try:
            if not os.path.exists(self._storage_dir):
                return

            for filename in os.listdir(self._storage_dir):
                if not filename.endswith(".json"):
                    continue

                filepath = os.path.join(self._storage_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        task_data = json.load(f)
                    task_id = task_data.get("task_id")
                    if task_id:
                        self.tasks[task_id] = TaskProgress(**task_data)
                except Exception as exc:
                    print(f"读取任务文件失败 {filename}: {exc}")
        except Exception as exc:
            print(f"加载任务目录失败: {exc}")

    def _save_task(self, task: TaskProgress):
        try:
            filepath = os.path.join(self._storage_dir, f"{task.task_id}.json")
            task_dict = asdict(task)
            if isinstance(task_dict["status"], TaskStatus):
                task_dict["status"] = task_dict["status"].value

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(task_dict, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"保存任务进度失败: {exc}")

    def create_task(self, total_steps: int, metadata: Optional[Dict] = None) -> str:
        task_id = str(uuid.uuid4())
        task = TaskProgress(
            task_id=task_id,
            status=TaskStatus.PENDING.value,
            progress=0.0,
            current_step="",
            total_steps=total_steps,
            current_step_index=0,
            start_time=datetime.now().isoformat(),
            metadata=metadata or {},
        )
        self.tasks[task_id] = task
        self._save_task(task)
        return task_id

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[float] = None,
        current_step: Optional[str] = None,
        current_step_index: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        if task_id not in self.tasks:
            raise ValueError(f"任务 ID 不存在: {task_id}")

        task = self.tasks[task_id]

        if status:
            task.status = status.value
        if progress is not None:
            task.progress = min(100.0, max(0.0, progress))
        if current_step is not None:
            task.current_step = current_step
        if current_step_index is not None:
            task.current_step_index = current_step_index
        if error_message is not None:
            task.error_message = error_message

        if status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            task.end_time = datetime.now().isoformat()

        self._save_task(task)

    def get_task(self, task_id: str) -> Optional[TaskProgress]:
        if task_id not in self.tasks:
            self.load_tasks_from_disk()
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[TaskProgress]:
        self.load_tasks_from_disk()
        return list(self.tasks.values())

    def delete_task(self, task_id: str):
        if task_id in self.tasks:
            del self.tasks[task_id]
            filepath = os.path.join(self._storage_dir, f"{task_id}.json")
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as exc:
                print(f"删除任务文件失败: {exc}")

    def cleanup_old_tasks(self, days: int = 7):
        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
        tasks_to_delete = []

        for task_id, task in self.tasks.items():
            try:
                start_time = datetime.fromisoformat(task.start_time)
                if start_time.timestamp() < cutoff_time:
                    tasks_to_delete.append(task_id)
            except Exception:
                pass

        for task_id in tasks_to_delete:
            self.delete_task(task_id)

        return len(tasks_to_delete)

    def repair_stale_processing_tasks(
        self,
        max_age_hours: float = 1.0,
        reason: Optional[str] = None,
        task_ids: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> List[TaskProgress]:
        self.load_tasks_from_disk()

        repaired_tasks: List[TaskProgress] = []
        selected_ids = set(task_ids or [])
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        repair_reason = reason or "Task recovered by repair script: stale processing task."

        for task in self.tasks.values():
            if task.status != TaskStatus.PROCESSING.value:
                continue

            if selected_ids and task.task_id not in selected_ids:
                continue

            if not selected_ids:
                try:
                    start_time = datetime.fromisoformat(task.start_time)
                except Exception:
                    start_time = None

                if start_time and start_time > cutoff_time:
                    continue

            repaired_task = TaskProgress(**asdict(task))
            repaired_task.status = TaskStatus.FAILED.value
            repaired_task.end_time = datetime.now().isoformat()
            repaired_task.error_message = repair_reason
            repaired_tasks.append(repaired_task)

            if not dry_run:
                self.tasks[task.task_id] = repaired_task
                self._save_task(repaired_task)

        return repaired_tasks
