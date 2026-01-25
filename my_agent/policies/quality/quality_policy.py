"""
QualityPolicy - Abstract interface for quality assessment.

Responsible for:
- Assessing step output quality
- Deciding when to retry steps
- Final plan quality assessment
"""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from ..base_policy import PolicyContext
from ...core.step import Step, StepResult


class QualityAssessment(BaseModel):
    """
    Result of a quality assessment.

    Used by QualityPolicy to communicate assessment results
    to the orchestrator.
    """
    passed: bool = Field(
        description="Whether the output meets acceptance criteria"
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Quality score from 0.0 to 1.0"
    )
    feedback: str = Field(
        default="",
        description="Human-readable feedback about the output"
    )
    issues: list[str] = Field(
        default_factory=list,
        description="List of specific issues found"
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Suggestions for improvement"
    )
    details: dict[str, float] = Field(
        default_factory=dict,
        description="Detailed scores by category"
    )


class QualityPolicy(ABC):
    """
    Abstract base class for quality policies.

    Implementations should:
    - Assess step outputs against acceptance criteria
    - Decide when retry is appropriate
    - Assess overall plan completion quality
    """

    @abstractmethod
    async def assess_step_output(
        self,
        step: Step,
        result: StepResult,
        ctx: PolicyContext,
    ) -> QualityAssessment:
        """
        Assess the quality of a step's output.

        Args:
            step: The step that was executed
            result: The step's execution result
            ctx: Current policy context

        Returns:
            QualityAssessment with score and feedback
        """
        pass

    @abstractmethod
    async def should_retry(
        self,
        step: Step,
        result: StepResult,
        assessment: QualityAssessment,
        ctx: PolicyContext,
    ) -> tuple[bool, str]:
        """
        Decide if a step should be retried.

        Called when step output doesn't meet quality criteria.

        Args:
            step: The step that was executed
            result: The step's execution result
            assessment: Quality assessment result
            ctx: Current policy context

        Returns:
            Tuple of (should_retry, reason/guidance)
        """
        pass

    @abstractmethod
    async def assess_plan_output(
        self,
        ctx: PolicyContext,
    ) -> QualityAssessment:
        """
        Assess the overall quality of plan execution.

        Called when all steps are complete to evaluate
        whether the goal has been achieved.

        Args:
            ctx: Current policy context with completed plan

        Returns:
            QualityAssessment for the entire plan
        """
        pass

    async def get_improvement_prompt(
        self,
        step: Step,
        result: StepResult,
        assessment: QualityAssessment,
    ) -> str:
        """
        Generate a prompt to guide retry improvement.

        Default implementation combines issues and suggestions.

        Args:
            step: The step to retry
            result: Previous execution result
            assessment: Quality assessment

        Returns:
            Prompt text to improve output
        """
        lines = [
            f"Previous attempt for '{step.name}' did not meet quality criteria.",
            f"Score: {assessment.score:.2f}",
            "",
        ]

        if assessment.issues:
            lines.append("Issues found:")
            for issue in assessment.issues:
                lines.append(f"  - {issue}")
            lines.append("")

        if assessment.suggestions:
            lines.append("Suggestions for improvement:")
            for suggestion in assessment.suggestions:
                lines.append(f"  - {suggestion}")
            lines.append("")

        lines.append("Please address these issues in your next attempt.")

        return "\n".join(lines)

    def calculate_aggregate_score(
        self,
        assessments: list[QualityAssessment],
    ) -> float:
        """
        Calculate aggregate score from multiple assessments.

        Default implementation uses weighted average.

        Args:
            assessments: List of assessments

        Returns:
            Aggregate score
        """
        if not assessments:
            return 0.0

        return sum(a.score for a in assessments) / len(assessments)
