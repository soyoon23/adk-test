"""
SelectionPolicy - Abstract interface for step selection.

Responsible for:
- Selecting the next step to execute from ready steps
- Scoring steps for prioritization
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..base_policy import PolicyContext
from ...core.step import Step


class SelectionPolicy(ABC):
    """
    Abstract base class for selection policies.

    Implementations should:
    - Choose the best next step from available ready steps
    - Score steps based on various criteria
    """

    @abstractmethod
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
        pass

    @abstractmethod
    def get_step_score(
        self,
        step: Step,
        ctx: PolicyContext,
    ) -> float:
        """
        Calculate a score for a step.

        Higher scores indicate higher priority.

        Args:
            step: Step to score
            ctx: Current policy context

        Returns:
            Score value (higher = more important)
        """
        pass

    def filter_steps(
        self,
        steps: list[Step],
        ctx: PolicyContext,
    ) -> list[Step]:
        """
        Filter steps before selection.

        Default implementation returns all steps.

        Args:
            steps: Steps to filter
            ctx: Current policy context

        Returns:
            Filtered list of steps
        """
        return steps

    def rank_steps(
        self,
        steps: list[Step],
        ctx: PolicyContext,
    ) -> list[tuple[Step, float]]:
        """
        Rank steps by their scores.

        Args:
            steps: Steps to rank
            ctx: Current policy context

        Returns:
            List of (step, score) tuples, sorted by score descending
        """
        scored = [(step, self.get_step_score(step, ctx)) for step in steps]
        return sorted(scored, key=lambda x: x[1], reverse=True)
