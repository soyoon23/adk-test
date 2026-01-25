"""
Step data models for defining task units.

A Step represents a single unit of work in a Plan:
- Has a type (GATHER, ANALYZE, DRAFT, etc.)
- Specifies input/output artifact IDs
- Contains acceptance criteria for quality gates
- Has budget constraints (tool calls, LLM calls, timeout)
- Tracks execution status and results
"""

from enum import Enum
from typing import Optional, Any
from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class StepType(Enum):
    """Types of steps that can be executed."""
    GATHER = "gather"       # Collect information/data
    ANALYZE = "analyze"     # Analyze data/artifacts
    DRAFT = "draft"         # Create initial content
    REFINE = "refine"       # Improve existing content
    RENDER = "render"       # Generate final output format
    VERIFY = "verify"       # Validate/check quality
    TRANSFORM = "transform" # Convert between formats
    CUSTOM = "custom"       # Custom step type


class StepStatus(Enum):
    """Execution status of a step."""
    PENDING = "pending"           # Not yet started
    READY = "ready"               # Dependencies met, ready to execute
    IN_PROGRESS = "in_progress"   # Currently executing
    COMPLETED = "completed"       # Successfully completed
    FAILED = "failed"             # Execution failed
    SKIPPED = "skipped"           # Skipped (e.g., conditional)
    BLOCKED = "blocked"           # Blocked by failed dependency


class AcceptanceCriteria(BaseModel):
    """
    Criteria for determining if a step's output is acceptable.

    Used by QualityPolicy to assess step results.
    """
    description: str = Field(
        description="Human-readable description of what constitutes success"
    )
    validation_prompt: str = Field(
        description="Prompt for LLM to validate output quality"
    )
    required_outputs: list[str] = Field(
        default_factory=list,
        description="List of required output artifact types or names"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts before marking as failed"
    )
    min_quality_score: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum quality score (0.0-1.0) to pass"
    )


class StepBudget(BaseModel):
    """
    Resource budget constraints for step execution.

    Prevents runaway execution and ensures predictable behavior.
    """
    max_tool_calls: int = Field(
        default=10,
        ge=1,
        description="Maximum number of tool calls allowed"
    )
    max_llm_calls: int = Field(
        default=5,
        ge=1,
        description="Maximum number of LLM invocations allowed"
    )
    timeout_seconds: int = Field(
        default=300,
        ge=1,
        description="Maximum execution time in seconds"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Optional token limit for LLM responses"
    )


class StepResult(BaseModel):
    """
    Result of executing a step.

    Captures outputs, metrics, and any errors from execution.
    """
    step_id: str = Field(
        description="ID of the step that was executed"
    )
    status: StepStatus = Field(
        description="Final status after execution"
    )
    output_artifact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of artifacts produced by this step"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if step failed"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="When execution started"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When execution completed"
    )
    tool_calls_used: int = Field(
        default=0,
        description="Number of tool calls made"
    )
    llm_calls_used: int = Field(
        default=0,
        description="Number of LLM calls made"
    )
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts"
    )
    quality_score: Optional[float] = Field(
        default=None,
        description="Quality assessment score (0.0-1.0)"
    )
    quality_feedback: Optional[str] = Field(
        default=None,
        description="Feedback from quality assessment"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional execution metadata"
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_success(self) -> bool:
        """Check if step completed successfully."""
        return self.status == StepStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        """Check if step failed."""
        return self.status == StepStatus.FAILED


class Step(BaseModel):
    """
    A single task unit in a Plan.

    Steps form a DAG (Directed Acyclic Graph) through depends_on references.
    """
    step_id: str = Field(
        description="Unique identifier for this step"
    )
    name: str = Field(
        description="Human-readable name for the step"
    )
    description: str = Field(
        description="Detailed description of what this step does"
    )
    step_type: StepType = Field(
        description="Type classification for this step"
    )
    instruction: str = Field(
        default="",
        description="Specific instruction for executing this step"
    )
    input_artifact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of artifacts required as input"
    )
    output_artifact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of artifacts produced as output (filled after execution)"
    )
    acceptance: AcceptanceCriteria = Field(
        default_factory=lambda: AcceptanceCriteria(
            description="Step completes successfully",
            validation_prompt="Did the step complete its task correctly?",
        ),
        description="Criteria for accepting step output"
    )
    budget: StepBudget = Field(
        default_factory=StepBudget,
        description="Resource budget for execution"
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of steps that must complete before this one"
    )
    status: StepStatus = Field(
        default=StepStatus.PENDING,
        description="Current execution status"
    )
    priority: int = Field(
        default=0,
        description="Priority for selection (higher = more important)"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional step metadata"
    )

    @classmethod
    def generate_id(cls) -> str:
        """Generate a new step ID."""
        return f"step-{uuid.uuid4().hex[:8]}"

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        step_type: StepType,
        instruction: str = "",
        input_artifact_ids: Optional[list[str]] = None,
        depends_on: Optional[list[str]] = None,
        acceptance: Optional[AcceptanceCriteria] = None,
        budget: Optional[StepBudget] = None,
        priority: int = 0,
        tags: Optional[list[str]] = None,
    ) -> "Step":
        """
        Factory method to create a new Step.

        Args:
            name: Human-readable name
            description: What this step does
            step_type: Type classification
            instruction: Execution instruction
            input_artifact_ids: Required input artifacts
            depends_on: Dependency step IDs
            acceptance: Acceptance criteria
            budget: Resource budget
            priority: Selection priority
            tags: Categorization tags

        Returns:
            New Step instance
        """
        return cls(
            step_id=cls.generate_id(),
            name=name,
            description=description,
            step_type=step_type,
            instruction=instruction,
            input_artifact_ids=input_artifact_ids or [],
            depends_on=depends_on or [],
            acceptance=acceptance or AcceptanceCriteria(
                description=f"{name} completes successfully",
                validation_prompt=f"Did '{name}' complete correctly and produce valid output?",
            ),
            budget=budget or StepBudget(),
            priority=priority,
            tags=tags or [],
        )

    def is_ready(self, completed_step_ids: set[str]) -> bool:
        """
        Check if this step is ready to execute.

        Args:
            completed_step_ids: Set of step IDs that have completed

        Returns:
            True if all dependencies are satisfied
        """
        if self.status != StepStatus.PENDING:
            return False
        return all(dep_id in completed_step_ids for dep_id in self.depends_on)

    def mark_ready(self) -> None:
        """Mark step as ready for execution."""
        if self.status == StepStatus.PENDING:
            self.status = StepStatus.READY

    def mark_in_progress(self) -> None:
        """Mark step as currently executing."""
        self.status = StepStatus.IN_PROGRESS

    def mark_completed(self, output_artifact_ids: Optional[list[str]] = None) -> None:
        """
        Mark step as successfully completed.

        Args:
            output_artifact_ids: IDs of produced artifacts
        """
        self.status = StepStatus.COMPLETED
        if output_artifact_ids:
            self.output_artifact_ids = output_artifact_ids

    def mark_failed(self) -> None:
        """Mark step as failed."""
        self.status = StepStatus.FAILED

    def mark_skipped(self) -> None:
        """Mark step as skipped."""
        self.status = StepStatus.SKIPPED

    def mark_blocked(self) -> None:
        """Mark step as blocked by failed dependency."""
        self.status = StepStatus.BLOCKED
