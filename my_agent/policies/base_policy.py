"""
Base policy context shared by all policy types.

PolicyContext provides all the information policies need
to make decisions, including:
- Current goal and plan
- Artifact store for data access
- Session state
- Execution history
"""

from typing import Optional, Any

from pydantic import BaseModel, Field

from ..core.plan import Plan
from ..core.step import StepResult
from ..core.artifact_store import ArtifactStore


class PolicyContext(BaseModel):
    """
    Shared context for all policy decisions.

    Provides read access to current state and write access
    to the artifact store.
    """

    model_config = {"arbitrary_types_allowed": True}

    goal: str = Field(
        description="The high-level goal being pursued"
    )
    current_plan: Optional[Plan] = Field(
        default=None,
        description="The current execution plan"
    )
    artifact_store: ArtifactStore = Field(
        default_factory=ArtifactStore,
        description="Store for artifacts produced by steps"
    )
    session_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Session state from ADK InvocationContext"
    )
    execution_history: list[StepResult] = Field(
        default_factory=list,
        description="History of step execution results"
    )
    iteration: int = Field(
        default=0,
        description="Current iteration number in orchestrator loop"
    )
    max_iterations: int = Field(
        default=50,
        description="Maximum iterations allowed"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context metadata"
    )

    def get_completed_artifacts(self) -> list[str]:
        """Get IDs of all artifacts from completed steps."""
        artifact_ids = []
        for result in self.execution_history:
            if result.is_success:
                artifact_ids.extend(result.output_artifact_ids)
        return artifact_ids

    def get_last_result(self) -> Optional[StepResult]:
        """Get the most recent step result."""
        if self.execution_history:
            return self.execution_history[-1]
        return None

    def get_failed_steps(self) -> list[StepResult]:
        """Get all failed step results."""
        return [r for r in self.execution_history if r.is_failure]

    def add_result(self, result: StepResult) -> None:
        """Add a step result to history."""
        self.execution_history.append(result)
        if self.current_plan:
            self.current_plan.record_step_result(result)

    def update_session_state(self, key: str, value: Any) -> None:
        """Update a session state value."""
        self.session_state[key] = value

    def get_session_state(self, key: str, default: Any = None) -> Any:
        """Get a session state value."""
        return self.session_state.get(key, default)

    def increment_iteration(self) -> int:
        """Increment and return the iteration counter."""
        self.iteration += 1
        return self.iteration

    def is_max_iterations_reached(self) -> bool:
        """Check if maximum iterations have been reached."""
        return self.iteration >= self.max_iterations

    def to_context_string(self) -> str:
        """
        Generate a string representation for LLM context.

        Returns:
            Context summary suitable for LLM consumption
        """
        lines = [
            f"Goal: {self.goal}",
            f"Iteration: {self.iteration}/{self.max_iterations}",
            "",
        ]

        if self.current_plan:
            lines.append(self.current_plan.to_context_string())
        else:
            lines.append("No plan created yet.")

        lines.append("")
        lines.append(self.artifact_store.get_context_summary())

        if self.execution_history:
            lines.extend([
                "",
                f"Execution history: {len(self.execution_history)} steps completed",
            ])
            last = self.get_last_result()
            if last:
                lines.append(f"Last step: {last.step_id} ({last.status.value})")

        return "\n".join(lines)
