"""
PrioritySelector - Priority-based selection policy.

Selects the next step based on:
- Step priority (higher = more important)
- Step type preferences
- Dependency readiness
"""

import logging
from typing import Optional

from .selection_policy import SelectionPolicy
from ..base_policy import PolicyContext
from ...core.step import Step, StepType


logger = logging.getLogger(__name__)


# Default weights for step types
DEFAULT_TYPE_WEIGHTS = {
    StepType.GATHER.value: 1.0,
    StepType.ANALYZE.value: 0.9,
    StepType.DRAFT.value: 0.8,
    StepType.REFINE.value: 0.7,
    StepType.VERIFY.value: 0.6,
    StepType.RENDER.value: 0.5,
    StepType.TRANSFORM.value: 0.4,
    StepType.CUSTOM.value: 0.3,
}


class PrioritySelector(SelectionPolicy):
    """
    Priority-based step selection policy.

    Selects steps based on explicit priority values,
    with tiebreakers based on step type and creation order.
    """

    def __init__(
        self,
        type_weights: Optional[dict[str, float]] = None,
        prefer_critical_path: bool = True,
        max_parallel: int = 1,
    ):
        """
        Initialize the priority selector.

        Args:
            type_weights: Custom weights for step types
            prefer_critical_path: Whether to prefer critical path steps
            max_parallel: Max steps to select (for parallel execution)
        """
        self.type_weights = type_weights or DEFAULT_TYPE_WEIGHTS.copy()
        self.prefer_critical_path = prefer_critical_path
        self.max_parallel = max_parallel

    async def select_next_step(
        self,
        ready_steps: list[Step],
        ctx: PolicyContext,
    ) -> Optional[Step]:
        """
        Select the next step to execute.

        Args:
            ready_steps: Steps that are ready to execute
            ctx: Current policy context

        Returns:
            Selected step, or None if no step should be executed
        """
        if not ready_steps:
            logger.info("No ready steps to select from")
            return None

        # Filter steps
        filtered = self.filter_steps(ready_steps, ctx)
        if not filtered:
            logger.info("All ready steps filtered out")
            return None

        # Rank by score
        ranked = self.rank_steps(filtered, ctx)

        if ranked:
            selected, score = ranked[0]
            logger.info(
                f"Selected step: {selected.name} ({selected.step_id}) "
                f"with score {score:.2f}"
            )
            return selected

        return None

    def get_step_score(
        self,
        step: Step,
        ctx: PolicyContext,
    ) -> float:
        """
        Calculate a score for a step.

        Score components:
        - Base priority (0-100 normalized)
        - Type weight (0-1)
        - Critical path bonus (if enabled)
        - Freshness (steps with fewer retries preferred)

        Args:
            step: Step to score
            ctx: Current policy context

        Returns:
            Score value (higher = more important)
        """
        score = 0.0

        # Base priority (normalized to 0-1 range, assuming max priority is 10)
        priority_score = min(step.priority / 10.0, 1.0) * 50
        score += priority_score

        # Type weight
        type_weight = self.type_weights.get(step.step_type.value, 0.5)
        score += type_weight * 30

        # Critical path bonus
        if self.prefer_critical_path and ctx.current_plan:
            dependents = self._count_dependents(step, ctx)
            critical_bonus = min(dependents / 5.0, 1.0) * 15
            score += critical_bonus

        # Retry penalty (prefer steps that haven't been retried)
        retry_penalty = 0
        for result in ctx.execution_history:
            if result.step_id == step.step_id:
                retry_penalty += result.retry_count * 5
        score -= retry_penalty

        return max(score, 0.0)

    def filter_steps(
        self,
        steps: list[Step],
        ctx: PolicyContext,
    ) -> list[Step]:
        """
        Filter steps before selection.

        Removes steps that:
        - Have exceeded retry limits
        - Are blocked by configuration

        Args:
            steps: Steps to filter
            ctx: Current policy context

        Returns:
            Filtered list of steps
        """
        filtered = []

        for step in steps:
            # Check retry count
            retry_count = self._get_retry_count(step, ctx)
            if retry_count >= step.acceptance.max_retries:
                logger.debug(
                    f"Filtering out {step.name}: max retries exceeded"
                )
                continue

            filtered.append(step)

        return filtered

    def _count_dependents(self, step: Step, ctx: PolicyContext) -> int:
        """
        Count how many other steps depend on this step.

        More dependents = higher critical path importance.
        """
        if not ctx.current_plan:
            return 0

        count = 0
        for other_step in ctx.current_plan.steps:
            if step.step_id in other_step.depends_on:
                count += 1

        return count

    def _get_retry_count(self, step: Step, ctx: PolicyContext) -> int:
        """Get the current retry count for a step."""
        for result in reversed(ctx.execution_history):
            if result.step_id == step.step_id:
                return result.retry_count
        return 0

    def select_parallel_steps(
        self,
        ready_steps: list[Step],
        ctx: PolicyContext,
    ) -> list[Step]:
        """
        Select multiple steps for parallel execution.

        Future enhancement for parallel step execution.

        Args:
            ready_steps: Steps that are ready to execute
            ctx: Current policy context

        Returns:
            List of selected steps (up to max_parallel)
        """
        if not ready_steps:
            return []

        filtered = self.filter_steps(ready_steps, ctx)
        ranked = self.rank_steps(filtered, ctx)

        # Select top N steps that don't conflict
        selected = []
        for step, score in ranked:
            if len(selected) >= self.max_parallel:
                break
            # For now, just take top N
            # Future: Check for conflicts
            selected.append(step)

        return selected
