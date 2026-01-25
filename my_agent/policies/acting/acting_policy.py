"""
ActingPolicy - Abstract interface for step execution.

Responsible for:
- Executing individual steps
- Managing tool calls and LLM interactions
- Producing step results with artifacts
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any

from ..base_policy import PolicyContext
from ...core.step import Step, StepResult


class ActingPolicy(ABC):
    """
    Abstract base class for acting policies.

    Implementations should:
    - Execute steps according to their instructions
    - Manage resource budgets
    - Produce artifacts and results
    """

    @abstractmethod
    async def execute_step(
        self,
        step: Step,
        ctx: PolicyContext,
        invocation_context: Any,
    ) -> AsyncGenerator[Any, None]:
        """
        Execute a step and yield events.

        Args:
            step: Step to execute
            ctx: Current policy context
            invocation_context: ADK InvocationContext

        Yields:
            Events from step execution
        """
        pass

    @abstractmethod
    async def get_step_result(
        self,
        step: Step,
        ctx: PolicyContext,
    ) -> StepResult:
        """
        Get the result after step execution.

        Called after execute_step completes to gather results.

        Args:
            step: Step that was executed
            ctx: Current policy context

        Returns:
            StepResult with status and artifacts
        """
        pass

    async def prepare_step(
        self,
        step: Step,
        ctx: PolicyContext,
    ) -> dict[str, Any]:
        """
        Prepare context for step execution.

        Default implementation loads input artifacts.

        Args:
            step: Step to prepare
            ctx: Current policy context

        Returns:
            Dict of prepared inputs
        """
        inputs = {}

        # Load input artifacts
        for artifact_id in step.input_artifact_ids:
            artifact = ctx.artifact_store.get_artifact(artifact_id)
            if artifact:
                inputs[artifact_id] = {
                    "metadata": artifact.metadata.model_dump(),
                    "preview": artifact.content_preview,
                }

        # Add session state
        inputs["session_state"] = ctx.session_state

        return inputs

    async def cleanup_step(
        self,
        step: Step,
        ctx: PolicyContext,
        result: StepResult,
    ) -> None:
        """
        Cleanup after step execution.

        Default implementation is a no-op.

        Args:
            step: Step that was executed
            ctx: Current policy context
            result: Step execution result
        """
        pass

    def is_budget_exceeded(
        self,
        step: Step,
        tool_calls: int,
        llm_calls: int,
    ) -> bool:
        """
        Check if step budget has been exceeded.

        Args:
            step: Step being executed
            tool_calls: Current tool call count
            llm_calls: Current LLM call count

        Returns:
            True if budget exceeded
        """
        return (
            tool_calls > step.budget.max_tool_calls or
            llm_calls > step.budget.max_llm_calls
        )
