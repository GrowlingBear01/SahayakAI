from threading import Lock

from .schemas import Task


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = Lock()

    def create(self, task: Task) -> Task:
        with self._lock:
            if task.task_id in self._tasks:
                raise ValueError(f"task already exists: {task.task_id}")
            self._tasks[task.task_id] = task
            return task.model_copy(deep=True)

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.model_copy(deep=True) if task else None

    def replace(self, task: Task) -> Task:
        with self._lock:
            if task.task_id not in self._tasks:
                raise KeyError(f"task not found: {task.task_id}")
            self._tasks[task.task_id] = task
            return task.model_copy(deep=True)


task_store = TaskStore()
