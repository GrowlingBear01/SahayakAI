import asyncio

from backend.planner import PlannerResult
from backend.schemas import Task, TaskState


DEMO_REQUEST = (
    "Fill the demo form for Savitri Devi, age 72, in Delhi, "
    "phone 9876543210."
)


class CompleteDemoPlanner:
    async def plan(self, transcript, language, flows, values) -> PlannerResult:
        return PlannerResult(
            flow_id="mock_scheme_application",
            values={
                "full_name": "Savitri Devi",
                "age": 72,
                "state": "Delhi",
                "phone": "9876543210",
            },
            missing=[],
            language="en",
            clarifying_question_en="",
            clarifying_question_hi="",
        )


async def wait_for_planner(orchestrator, task_id: str) -> Task:
    for _ in range(2000):
        task = orchestrator.store.get(task_id)
        if task is None:
            raise AssertionError("task disappeared while planner was running")
        if task.state != TaskState.PLANNING:
            return task
        await asyncio.sleep(0.001)
    raise AssertionError("planner did not finish within two seconds")
