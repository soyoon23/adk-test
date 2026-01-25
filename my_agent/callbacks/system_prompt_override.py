"""
System prompt override callback for ADK.

Provides a before_model_callback that dynamically overrides
the system instruction based on current execution context.
"""

import logging
from typing import Callable, Optional, Any

from ..core.step import Step
from ..policies.base_policy import PolicyContext


logger = logging.getLogger(__name__)


def create_system_prompt_override(
    instruction_provider: Callable[[Any], str],
) -> Callable[[Any, Any], Optional[Any]]:
    """
    Create a before_model_callback that overrides system instructions.

    The instruction_provider function receives the callback_context
    and returns the new system instruction to use.

    Args:
        instruction_provider: Function that takes callback_context
                              and returns the system instruction string

    Returns:
        A before_model_callback function for use with ADK agents

    Example:
        ```python
        def my_instruction_provider(callback_context):
            step = callback_context.get("current_step")
            if step:
                return f"Execute step: {step.name}\\n{step.instruction}"
            return "Default instruction"

        callback = create_system_prompt_override(my_instruction_provider)

        agent = LlmAgent(
            name="MyAgent",
            model=model,
            before_model_callback=callback,
        )
        ```
    """
    def before_model_callback(
        callback_context: Any,
        llm_request: Any,
    ) -> Optional[Any]:
        """
        Override the system instruction before LLM call.

        Args:
            callback_context: ADK callback context
            llm_request: The LLM request being prepared

        Returns:
            None to continue with modified request,
            or a response to short-circuit the call
        """
        try:
            # Get new instruction from provider
            new_instruction = instruction_provider(callback_context)

            if new_instruction and llm_request.config:
                # Override system instruction
                llm_request.config.system_instruction = new_instruction
                logger.debug(
                    f"System instruction overridden: {new_instruction[:100]}..."
                )

        except Exception as e:
            logger.warning(f"Failed to override system prompt: {e}")

        # Return None to continue with the (possibly modified) request
        return None

    return before_model_callback


def create_step_instruction_provider(
    policy_context: PolicyContext,
    base_instruction: str = "",
) -> Callable[[Any], str]:
    """
    Create an instruction provider for step-based execution.

    Generates instructions that include:
    - Current step details
    - Available artifacts
    - Execution context

    Args:
        policy_context: The policy context with current state
        base_instruction: Base instruction to prepend

    Returns:
        An instruction provider function
    """
    def instruction_provider(callback_context: Any) -> str:
        """Generate instruction based on current step."""
        lines = []

        # Add base instruction
        if base_instruction:
            lines.append(base_instruction)
            lines.append("")

        # Add context summary
        lines.append("CONTEXT:")
        lines.append(policy_context.to_context_string())
        lines.append("")

        # Get current step from context if available
        current_step = None
        if hasattr(callback_context, "get"):
            current_step = callback_context.get("current_step")
        elif hasattr(callback_context, "current_step"):
            current_step = callback_context.current_step

        # Add step-specific instruction
        if current_step and isinstance(current_step, Step):
            lines.append("CURRENT STEP:")
            lines.append(f"Name: {current_step.name}")
            lines.append(f"Type: {current_step.step_type.value}")
            lines.append(f"Description: {current_step.description}")
            lines.append("")
            lines.append("INSTRUCTION:")
            lines.append(current_step.instruction or current_step.description)
            lines.append("")

            # Add input artifacts
            if current_step.input_artifact_ids:
                lines.append("INPUT ARTIFACTS:")
                for artifact_id in current_step.input_artifact_ids:
                    artifact = policy_context.artifact_store.get_artifact(artifact_id)
                    if artifact:
                        lines.append(
                            f"- [{artifact_id}] {artifact.metadata.filename}: "
                            f"{artifact.metadata.description}"
                        )
                lines.append("")

            # Add acceptance criteria
            lines.append("ACCEPTANCE CRITERIA:")
            lines.append(current_step.acceptance.description)

        return "\n".join(lines)

    return instruction_provider


class StepAwareCallback:
    """
    A callback class that maintains step awareness across calls.

    Useful when you need to track state across multiple callback invocations.
    """

    def __init__(
        self,
        policy_context: PolicyContext,
        base_instruction: str = "",
    ):
        """
        Initialize the callback.

        Args:
            policy_context: Policy context for state access
            base_instruction: Base instruction to use
        """
        self.policy_context = policy_context
        self.base_instruction = base_instruction
        self.current_step: Optional[Step] = None
        self.call_count = 0

    def set_current_step(self, step: Optional[Step]) -> None:
        """Set the current step being executed."""
        self.current_step = step

    def __call__(
        self,
        callback_context: Any,
        llm_request: Any,
    ) -> Optional[Any]:
        """
        Handle the callback invocation.

        Args:
            callback_context: ADK callback context
            llm_request: The LLM request

        Returns:
            None to continue
        """
        self.call_count += 1

        try:
            instruction = self._build_instruction()

            if instruction and llm_request.config:
                llm_request.config.system_instruction = instruction

        except Exception as e:
            logger.warning(f"StepAwareCallback error: {e}")

        return None

    def _build_instruction(self) -> str:
        """Build the instruction string."""
        lines = []

        if self.base_instruction:
            lines.append(self.base_instruction)
            lines.append("")

        if self.current_step:
            lines.append(f"STEP: {self.current_step.name}")
            lines.append(f"TYPE: {self.current_step.step_type.value}")
            lines.append("")
            lines.append("INSTRUCTION:")
            lines.append(self.current_step.instruction or self.current_step.description)
            lines.append("")
            lines.append("ACCEPTANCE:")
            lines.append(self.current_step.acceptance.description)

        # Add artifact summary
        artifacts = self.policy_context.artifact_store.list_artifacts()
        if artifacts:
            lines.append("")
            lines.append("AVAILABLE ARTIFACTS:")
            for a in artifacts[:10]:  # Limit to prevent context explosion
                lines.append(f"- [{a.metadata.artifact_id}] {a.metadata.filename}")

        return "\n".join(lines)
