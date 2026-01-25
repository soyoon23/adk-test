"""
PlanningPolicy - Abstract interface for plan creation and updates.

Responsible for:
- Creating initial plans from goals
- Deciding when to replan
- Updating plans based on execution results
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..base_policy import PolicyContext
from ...core.plan import Plan
from ...core.step import StepResult


class PlanningPolicy(ABC):
    """
    Abstract base class for planning policies.

    Implementations should decide:
    - How to decompose goals into steps
    - How to structure step dependencies
    - When replanning is necessary
    """

    @abstractmethod
    async def create_plan(self, ctx: PolicyContext) -> Plan:
        """
        Create an initial plan from the goal.

        Args:
            ctx: Current policy context with goal and state

        Returns:
            A new Plan with steps to achieve the goal
        """
        pass

    @abstractmethod
    async def update_plan(
        self,
        ctx: PolicyContext,
        step_result: StepResult,
    ) -> Optional[Plan]:
        """
        Update the plan based on a step result.

        Called after each step execution to allow plan modifications.

        Args:
            ctx: Current policy context
            step_result: Result of the just-completed step

        Returns:
            Updated Plan, or None if no changes needed
        """
        pass

    @abstractmethod
    async def should_replan(
        self,
        ctx: PolicyContext,
        step_result: StepResult,
    ) -> tuple[bool, str]:
        """
        Determine if replanning is needed.

        Called after step execution to decide if the current
        plan should be abandoned and a new plan created.

        Args:
            ctx: Current policy context
            step_result: Result of the just-completed step

        Returns:
            Tuple of (should_replan, reason)
        """
        pass

    async def validate_plan(self, plan: Plan) -> tuple[bool, Optional[str]]:
        """
        Validate a plan before execution.

        Default implementation checks DAG validity.

        Args:
            plan: Plan to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return plan.validate_dag()

    async def estimate_plan_effort(self, plan: Plan) -> dict[str, int]:
        """
        Estimate the effort required for a plan.

        Default implementation sums step budgets.

        Args:
            plan: Plan to estimate

        Returns:
            Dict with effort estimates
        """
        total_tool_calls = sum(s.budget.max_tool_calls for s in plan.steps)
        total_llm_calls = sum(s.budget.max_llm_calls for s in plan.steps)
        total_timeout = sum(s.budget.timeout_seconds for s in plan.steps)

        return {
            "total_steps": len(plan.steps),
            "max_tool_calls": total_tool_calls,
            "max_llm_calls": total_llm_calls,
            "max_timeout_seconds": total_timeout,
        }
