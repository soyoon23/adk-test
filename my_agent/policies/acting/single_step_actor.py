"""
SingleStepActor - Basic acting policy that executes one step at a time.

Uses an LLM agent to execute individual steps, managing:
- Step instruction formatting
- Budget tracking
- Artifact creation
- Result collection
"""

import logging
from typing import AsyncGenerator, Any, Optional
from datetime import datetime

from .acting_policy import ActingPolicy
from ..base_policy import PolicyContext
from ...core.step import Step, StepResult, StepStatus
from ...core.artifact import ArtifactType


logger = logging.getLogger(__name__)


# Prompt template for step execution
STEP_EXECUTION_PROMPT = """You are executing a specific step in a larger plan.

STEP: {step_name}
TYPE: {step_type}
DESCRIPTION: {step_description}

INSTRUCTION:
{instruction}

INPUT ARTIFACTS:
{input_artifacts}

CONTEXT:
{context}

Execute this step and produce the required output. Be thorough but focused on this specific step only.
"""


class SingleStepActor(ActingPolicy):
    """
    Simple acting policy that executes one step at a time.

    Uses the provided LLM model to execute step instructions
    and collects results into artifacts.
    """

    def __init__(self, model: Any, output_key_prefix: str = "step_output"):
        """
        Initialize the single step actor.

        Args:
            model: LLM model instance (e.g., LiteLlm)
            output_key_prefix: Prefix for output keys in session state
        """
        self.model = model
        self.output_key_prefix = output_key_prefix

        # Tracking state for current execution
        self._current_step: Optional[Step] = None
        self._tool_calls: int = 0
        self._llm_calls: int = 0
        self._started_at: Optional[datetime] = None
        self._output_content: str = ""
        self._error_message: Optional[str] = None

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
        logger.info(f"Executing step: {step.name} ({step.step_id})")

        # Initialize tracking
        self._current_step = step
        self._tool_calls = 0
        self._llm_calls = 0
        self._started_at = datetime.utcnow()
        self._output_content = ""
        self._error_message = None

        # Mark step as in progress
        step.mark_in_progress()

        try:
            # Prepare inputs
            inputs = await self.prepare_step(step, ctx)

            # Build execution prompt
            prompt = self._build_execution_prompt(step, inputs, ctx)

            # Execute via LLM
            # In a real implementation, this would use ADK's LlmAgent
            response = await self._execute_llm(prompt, step, ctx, invocation_context)

            self._output_content = response
            self._llm_calls += 1

            # Store output in session state
            output_key = f"{self.output_key_prefix}_{step.step_id}"
            ctx.update_session_state(output_key, response)

            logger.info(f"Step {step.name} execution completed")

            # Yield a completion event (simplified)
            yield {
                "type": "step_completed",
                "step_id": step.step_id,
                "output_preview": response[:200] if response else "",
            }

        except Exception as e:
            logger.error(f"Step {step.name} failed: {e}")
            self._error_message = str(e)

            yield {
                "type": "step_failed",
                "step_id": step.step_id,
                "error": str(e),
            }

    async def get_step_result(
        self,
        step: Step,
        ctx: PolicyContext,
    ) -> StepResult:
        """
        Get the result after step execution.

        Args:
            step: Step that was executed
            ctx: Current policy context

        Returns:
            StepResult with status and artifacts
        """
        completed_at = datetime.utcnow()

        # Determine status
        if self._error_message:
            status = StepStatus.FAILED
            step.mark_failed()
        else:
            status = StepStatus.COMPLETED
            step.mark_completed()

        # Create artifact if we have output
        output_artifact_ids = []
        if self._output_content and not self._error_message:
            artifact_id = ctx.artifact_store.save(
                content=self._output_content,
                artifact_type=self._determine_artifact_type(step),
                filename=f"{step.step_id}_output.txt",
                description=f"Output from step: {step.name}",
                created_by_step_id=step.step_id,
                tags=[step.step_type.value],
            )
            output_artifact_ids.append(artifact_id)

        result = StepResult(
            step_id=step.step_id,
            status=status,
            output_artifact_ids=output_artifact_ids,
            error_message=self._error_message,
            started_at=self._started_at,
            completed_at=completed_at,
            tool_calls_used=self._tool_calls,
            llm_calls_used=self._llm_calls,
        )

        # Cleanup
        await self.cleanup_step(step, ctx, result)

        return result

    def _build_execution_prompt(
        self,
        step: Step,
        inputs: dict[str, Any],
        ctx: PolicyContext,
    ) -> str:
        """Build the execution prompt for a step."""
        # Format input artifacts
        input_lines = []
        for artifact_id, artifact_info in inputs.items():
            if artifact_id == "session_state":
                continue
            if isinstance(artifact_info, dict):
                input_lines.append(
                    f"- [{artifact_id}]: {artifact_info.get('preview', 'No preview')}"
                )

        input_artifacts = "\n".join(input_lines) if input_lines else "No input artifacts"

        # Build context summary
        context_parts = [ctx.to_context_string()]

        return STEP_EXECUTION_PROMPT.format(
            step_name=step.name,
            step_type=step.step_type.value,
            step_description=step.description,
            instruction=step.instruction or step.description,
            input_artifacts=input_artifacts,
            context="\n".join(context_parts),
        )

    async def _execute_llm(
        self,
        prompt: str,
        step: Step,
        ctx: PolicyContext,
        invocation_context: Any,
    ) -> str:
        """
        Execute the LLM call for a step.

        In a real implementation, this would use ADK's LlmAgent.
        """
        logger.info(f"LLM execution for step: {step.name}")

        # This is a simplified implementation
        # In practice, you'd use the ADK's LLM calling mechanism

        # For now, return a placeholder response
        # Real implementation would use self.model and invocation_context

        # Check if we have the ADK context
        if invocation_context is not None:
            try:
                # Try to use actual LLM if available
                from google.adk.agents import LlmAgent
                from google.genai import types

                # Create a temporary agent for this step
                # Replace hyphens with underscores for valid agent name
                safe_name = step.step_id.replace("-", "_")
                temp_agent = LlmAgent(
                    name=f"StepExecutor_{safe_name}",
                    model=self.model,
                    instruction=prompt,
                )

                # Collect response
                response_parts = []
                async for event in temp_agent.run_async(invocation_context):
                    if hasattr(event, 'content') and event.content:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_parts.append(part.text)

                if response_parts:
                    return "\n".join(response_parts)

            except Exception as e:
                logger.warning(f"Failed to use ADK LLM: {e}, using fallback")

        # Fallback response
        return f"[Step {step.name} executed]\n\nThis is a placeholder output. In production, this would contain the actual LLM response for the step instruction:\n\n{step.instruction or step.description}"

    def _determine_artifact_type(self, step: Step) -> ArtifactType:
        """Determine the artifact type based on step type."""
        type_map = {
            "gather": ArtifactType.TEXT,
            "analyze": ArtifactType.DOCUMENT,
            "draft": ArtifactType.DOCUMENT,
            "refine": ArtifactType.DOCUMENT,
            "render": ArtifactType.DOCUMENT,
            "verify": ArtifactType.TEXT,
            "transform": ArtifactType.TEXT,
            "custom": ArtifactType.TEXT,
        }
        return type_map.get(step.step_type.value, ArtifactType.TEXT)

    async def cleanup_step(
        self,
        step: Step,
        ctx: PolicyContext,
        result: StepResult,
    ) -> None:
        """Cleanup after step execution."""
        # Reset tracking state
        self._current_step = None
        self._tool_calls = 0
        self._llm_calls = 0
        self._started_at = None
        self._output_content = ""
        self._error_message = None
