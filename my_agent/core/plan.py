"""
Plan data model for organizing steps into a DAG.

A Plan represents the complete execution strategy:
- Collection of Steps with dependencies (DAG structure)
- Version tracking for replanning
- Status tracking
- Methods to query ready steps and check completion
"""

from enum import Enum
from typing import Optional, Any
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from .step import Step, StepStatus, StepResult


class PlanStatus(Enum):
    """Status of the overall plan."""
    DRAFT = "draft"             # Plan is being created
    READY = "ready"             # Plan is ready to execute
    IN_PROGRESS = "in_progress" # Plan is being executed
    COMPLETED = "completed"     # All steps completed successfully
    FAILED = "failed"           # Plan failed (unrecoverable)
    REPLANNING = "replanning"   # Plan is being revised
    CANCELLED = "cancelled"     # Plan was cancelled


class Plan(BaseModel):
    """
    A plan consisting of Steps arranged in a DAG.

    Provides methods for:
    - Querying ready-to-execute steps
    - Checking completion status
    - Tracking execution progress
    - Managing replanning
    """
    plan_id: str = Field(
        description="Unique identifier for this plan"
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Version number (increments on replan)"
    )
    goal: str = Field(
        description="The high-level goal this plan achieves"
    )
    description: str = Field(
        default="",
        description="Detailed description of the plan"
    )
    steps: list[Step] = Field(
        default_factory=list,
        description="Steps in this plan"
    )
    status: PlanStatus = Field(
        default=PlanStatus.DRAFT,
        description="Current plan status"
    )
    parent_plan_id: Optional[str] = Field(
        default=None,
        description="ID of previous plan (if this is a replan)"
    )
    replan_reason: Optional[str] = Field(
        default=None,
        description="Reason for replanning (if applicable)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When plan was created"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="When execution started"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When execution completed"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional plan metadata"
    )
    execution_history: list[StepResult] = Field(
        default_factory=list,
        description="Results of executed steps"
    )

    @classmethod
    def generate_id(cls) -> str:
        """Generate a new plan ID."""
        return f"plan-{uuid.uuid4().hex[:8]}"

    @classmethod
    def create(
        cls,
        goal: str,
        steps: Optional[list[Step]] = None,
        description: str = "",
        parent_plan_id: Optional[str] = None,
        replan_reason: Optional[str] = None,
    ) -> "Plan":
        """
        Factory method to create a new Plan.

        Args:
            goal: High-level goal
            steps: Initial steps (can be added later)
            description: Plan description
            parent_plan_id: Previous plan ID if replanning
            replan_reason: Reason for replanning

        Returns:
            New Plan instance
        """
        version = 1
        if parent_plan_id:
            version = 1  # Will be set properly when linking to parent

        return cls(
            plan_id=cls.generate_id(),
            version=version,
            goal=goal,
            description=description,
            steps=steps or [],
            parent_plan_id=parent_plan_id,
            replan_reason=replan_reason,
        )

    def add_step(self, step: Step) -> None:
        """Add a step to the plan."""
        self.steps.append(step)

    def get_step(self, step_id: str) -> Optional[Step]:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_steps_by_status(self, status: StepStatus) -> list[Step]:
        """Get all steps with a specific status."""
        return [s for s in self.steps if s.status == status]

    def get_completed_step_ids(self) -> set[str]:
        """Get IDs of all completed steps."""
        return {s.step_id for s in self.steps if s.status == StepStatus.COMPLETED}

    def get_ready_steps(self) -> list[Step]:
        """
        Get all steps that are ready to execute.

        A step is ready if:
        - Its status is PENDING or READY
        - All its dependencies have completed

        Returns:
            List of ready steps, sorted by priority (highest first)
        """
        completed_ids = self.get_completed_step_ids()
        ready = []

        for step in self.steps:
            if step.status in (StepStatus.PENDING, StepStatus.READY):
                if step.is_ready(completed_ids):
                    step.mark_ready()
                    ready.append(step)

        # Sort by priority (higher first)
        return sorted(ready, key=lambda s: s.priority, reverse=True)

    def get_blocked_steps(self) -> list[Step]:
        """Get steps blocked by failed dependencies."""
        failed_ids = {s.step_id for s in self.steps if s.status == StepStatus.FAILED}
        blocked = []

        for step in self.steps:
            if step.status == StepStatus.PENDING:
                if any(dep_id in failed_ids for dep_id in step.depends_on):
                    step.mark_blocked()
                    blocked.append(step)

        return blocked

    def is_complete(self) -> bool:
        """
        Check if the plan is complete.

        A plan is complete when all non-skipped steps are completed.
        """
        for step in self.steps:
            if step.status not in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                return False
        return True

    def has_failures(self) -> bool:
        """Check if any steps have failed."""
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def has_in_progress(self) -> bool:
        """Check if any steps are currently in progress."""
        return any(s.status == StepStatus.IN_PROGRESS for s in self.steps)

    def get_progress(self) -> dict[str, int]:
        """
        Get execution progress statistics.

        Returns:
            Dict with counts by status
        """
        progress = {status.value: 0 for status in StepStatus}
        for step in self.steps:
            progress[step.status.value] += 1
        progress["total"] = len(self.steps)
        return progress

    def mark_ready(self) -> None:
        """Mark plan as ready to execute."""
        self.status = PlanStatus.READY

    def mark_in_progress(self) -> None:
        """Mark plan as in progress."""
        self.status = PlanStatus.IN_PROGRESS
        if not self.started_at:
            self.started_at = datetime.utcnow()

    def mark_completed(self) -> None:
        """Mark plan as completed."""
        self.status = PlanStatus.COMPLETED
        self.completed_at = datetime.utcnow()

    def mark_failed(self) -> None:
        """Mark plan as failed."""
        self.status = PlanStatus.FAILED
        self.completed_at = datetime.utcnow()

    def mark_replanning(self) -> None:
        """Mark plan as being replanned."""
        self.status = PlanStatus.REPLANNING

    def record_step_result(self, result: StepResult) -> None:
        """
        Record the result of a step execution.

        Args:
            result: The step execution result
        """
        self.execution_history.append(result)

        # Update step status
        step = self.get_step(result.step_id)
        if step:
            step.status = result.status
            if result.output_artifact_ids:
                step.output_artifact_ids = result.output_artifact_ids

    def create_replan(self, reason: str) -> "Plan":
        """
        Create a new plan version for replanning.

        Args:
            reason: Reason for replanning

        Returns:
            New Plan instance linked to this one
        """
        return Plan.create(
            goal=self.goal,
            description=self.description,
            parent_plan_id=self.plan_id,
            replan_reason=reason,
        )

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """
        Get the dependency graph as adjacency list.

        Returns:
            Dict mapping step_id to list of dependent step IDs
        """
        graph = {step.step_id: [] for step in self.steps}
        for step in self.steps:
            for dep_id in step.depends_on:
                if dep_id in graph:
                    graph[dep_id].append(step.step_id)
        return graph

    def validate_dag(self) -> tuple[bool, Optional[str]]:
        """
        Validate that steps form a valid DAG (no cycles).

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check all dependencies reference existing steps
        step_ids = {s.step_id for s in self.steps}
        for step in self.steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    return False, f"Step {step.step_id} depends on non-existent step {dep_id}"

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            step = self.get_step(step_id)
            if step:
                for dep_id in step.depends_on:
                    if dep_id not in visited:
                        if has_cycle(dep_id):
                            return True
                    elif dep_id in rec_stack:
                        return True

            rec_stack.remove(step_id)
            return False

        for step in self.steps:
            if step.step_id not in visited:
                if has_cycle(step.step_id):
                    return False, "Plan contains circular dependencies"

        return True, None

    def to_context_string(self) -> str:
        """
        Generate a string representation for LLM context.

        Returns:
            Plan summary suitable for LLM consumption
        """
        lines = [
            f"Plan: {self.plan_id} (v{self.version})",
            f"Goal: {self.goal}",
            f"Status: {self.status.value}",
            "",
            "Steps:",
        ]

        for step in self.steps:
            deps = f" (depends on: {', '.join(step.depends_on)})" if step.depends_on else ""
            lines.append(
                f"  - [{step.step_id}] {step.name} ({step.status.value}){deps}"
            )

        progress = self.get_progress()
        lines.extend([
            "",
            f"Progress: {progress['completed']}/{progress['total']} completed",
        ])

        return "\n".join(lines)
