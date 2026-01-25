"""
OrchestratorState - State model for orchestrator checkpointing.

Enables:
- Pause/resume of long-running workflows
- State persistence for recovery
- Progress tracking
"""

from enum import Enum
from typing import Optional, Any
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from ..core.plan import Plan, PlanStatus
from ..core.step import StepResult
from ..core.artifact_store import ArtifactStore


class OrchestratorPhase(Enum):
    """Current phase of the orchestrator state machine."""
    INITIALIZING = "initializing"
    PLANNING = "planning"
    SELECTING = "selecting"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    QUALITY_GATE = "quality_gate"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class OrchestratorState(BaseModel):
    """
    Complete state of an orchestrator execution.

    Can be serialized for checkpointing and restored for resumption.
    """

    model_config = {"arbitrary_types_allowed": True}

    # Identification
    execution_id: str = Field(
        default_factory=lambda: f"exec-{uuid.uuid4().hex[:8]}",
        description="Unique identifier for this execution"
    )

    # Goal and configuration
    goal: str = Field(
        description="The high-level goal being pursued"
    )
    max_iterations: int = Field(
        default=50,
        ge=1,
        description="Maximum orchestrator iterations"
    )

    # Current state
    phase: OrchestratorPhase = Field(
        default=OrchestratorPhase.INITIALIZING,
        description="Current phase of execution"
    )
    iteration: int = Field(
        default=0,
        description="Current iteration number"
    )

    # Plan state
    current_plan: Optional[Plan] = Field(
        default=None,
        description="Current execution plan"
    )
    plan_history: list[Plan] = Field(
        default_factory=list,
        description="History of plans (for replanning)"
    )

    # Step state
    current_step_id: Optional[str] = Field(
        default=None,
        description="ID of currently executing step"
    )
    pending_step_ids: list[str] = Field(
        default_factory=list,
        description="IDs of steps waiting to execute"
    )

    # Results
    execution_history: list[StepResult] = Field(
        default_factory=list,
        description="History of step execution results"
    )
    artifact_store: ArtifactStore = Field(
        default_factory=ArtifactStore,
        description="Store for artifacts"
    )

    # Session state (passed through from ADK)
    session_state: dict[str, Any] = Field(
        default_factory=dict,
        description="ADK session state"
    )

    # Timestamps
    started_at: Optional[datetime] = Field(
        default=None,
        description="When execution started"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When execution completed"
    )
    last_checkpoint_at: Optional[datetime] = Field(
        default=None,
        description="When last checkpoint was taken"
    )

    # Error tracking
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message if any"
    )
    error_count: int = Field(
        default=0,
        description="Count of errors encountered"
    )

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional state metadata"
    )

    @classmethod
    def create(
        cls,
        goal: str,
        max_iterations: int = 50,
        session_state: Optional[dict] = None,
    ) -> "OrchestratorState":
        """
        Create a new orchestrator state.

        Args:
            goal: The goal to achieve
            max_iterations: Maximum iterations
            session_state: Initial session state

        Returns:
            New OrchestratorState instance
        """
        return cls(
            goal=goal,
            max_iterations=max_iterations,
            session_state=session_state or {},
            started_at=datetime.utcnow(),
        )

    def transition_to(self, phase: OrchestratorPhase) -> None:
        """
        Transition to a new phase.

        Args:
            phase: The phase to transition to
        """
        self.phase = phase

        if phase == OrchestratorPhase.COMPLETED:
            self.completed_at = datetime.utcnow()
        elif phase == OrchestratorPhase.FAILED:
            self.completed_at = datetime.utcnow()

    def increment_iteration(self) -> int:
        """Increment and return the iteration counter."""
        self.iteration += 1
        return self.iteration

    def is_max_iterations_reached(self) -> bool:
        """Check if maximum iterations have been reached."""
        return self.iteration >= self.max_iterations

    def set_current_step(self, step_id: Optional[str]) -> None:
        """Set the currently executing step."""
        self.current_step_id = step_id

    def add_step_result(self, result: StepResult) -> None:
        """Add a step result to history."""
        self.execution_history.append(result)
        if self.current_plan:
            self.current_plan.record_step_result(result)

    def set_plan(self, plan: Plan) -> None:
        """Set the current plan."""
        if self.current_plan:
            self.plan_history.append(self.current_plan)
        self.current_plan = plan

    def record_error(self, error: str) -> None:
        """Record an error."""
        self.last_error = error
        self.error_count += 1

    def checkpoint(self) -> dict[str, Any]:
        """
        Create a checkpoint of the current state.

        Returns:
            Serializable state dictionary
        """
        self.last_checkpoint_at = datetime.utcnow()
        return self.model_dump(mode="json")

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> "OrchestratorState":
        """
        Restore state from a checkpoint.

        Args:
            data: Checkpoint data

        Returns:
            Restored OrchestratorState
        """
        return cls.model_validate(data)

    def get_progress(self) -> dict[str, Any]:
        """
        Get current progress information.

        Returns:
            Progress statistics
        """
        completed = len([r for r in self.execution_history if r.is_success])
        failed = len([r for r in self.execution_history if r.is_failure])
        total_steps = len(self.current_plan.steps) if self.current_plan else 0

        return {
            "execution_id": self.execution_id,
            "phase": self.phase.value,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "steps_completed": completed,
            "steps_failed": failed,
            "total_steps": total_steps,
            "artifacts_created": len(self.artifact_store.artifacts),
            "error_count": self.error_count,
        }

    def is_terminal(self) -> bool:
        """Check if in a terminal state."""
        return self.phase in (
            OrchestratorPhase.COMPLETED,
            OrchestratorPhase.FAILED,
        )

    def can_continue(self) -> bool:
        """Check if execution can continue."""
        return (
            not self.is_terminal() and
            not self.is_max_iterations_reached() and
            self.phase != OrchestratorPhase.PAUSED
        )
