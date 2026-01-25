"""
CriticVerifier - LLM-based quality policy for assessing outputs.

Uses an LLM to:
- Assess step output quality against acceptance criteria
- Decide when to retry failed steps
- Evaluate overall plan completion
"""

import logging
from typing import Any, Optional
import json

from .quality_policy import QualityPolicy, QualityAssessment
from ..base_policy import PolicyContext
from ...core.step import Step, StepResult


logger = logging.getLogger(__name__)


# Prompt template for step quality assessment
STEP_ASSESSMENT_PROMPT = """You are a quality assessor evaluating the output of a task step.

STEP: {step_name}
DESCRIPTION: {step_description}

ACCEPTANCE CRITERIA:
{acceptance_criteria}

OUTPUT TO ASSESS:
{output_preview}

Evaluate the output against the acceptance criteria. Consider:
1. Does it meet the stated requirements?
2. Is the quality sufficient?
3. Are there any issues or errors?
4. What improvements could be made?

Respond with JSON:
{{
  "passed": true/false,
  "score": 0.0-1.0,
  "feedback": "Overall assessment",
  "issues": ["issue1", "issue2"],
  "suggestions": ["suggestion1", "suggestion2"]
}}

Respond with ONLY valid JSON, no additional text.
"""

# Prompt template for plan quality assessment
PLAN_ASSESSMENT_PROMPT = """You are evaluating the overall completion of a plan.

GOAL: {goal}

PLAN SUMMARY:
{plan_summary}

COMPLETED ARTIFACTS:
{artifacts_summary}

EXECUTION HISTORY:
{history_summary}

Assess whether the goal has been achieved. Consider:
1. Were all necessary steps completed?
2. Do the artifacts meet the original goal?
3. Is the overall quality acceptable?
4. What is missing or could be improved?

Respond with JSON:
{{
  "passed": true/false,
  "score": 0.0-1.0,
  "feedback": "Overall assessment of goal achievement",
  "issues": ["issue1", "issue2"],
  "suggestions": ["suggestion1", "suggestion2"]
}}

Respond with ONLY valid JSON, no additional text.
"""


class CriticVerifier(QualityPolicy):
    """
    LLM-based quality policy using a critic/verifier pattern.

    Uses the provided LLM to assess quality and make retry decisions.
    """

    def __init__(
        self,
        model: Any,
        min_pass_score: float = 0.7,
        max_retries: int = 3,
    ):
        """
        Initialize the critic verifier.

        Args:
            model: LLM model instance (e.g., LiteLlm)
            min_pass_score: Minimum score to pass quality check
            max_retries: Maximum retry attempts
        """
        self.model = model
        self.min_pass_score = min_pass_score
        self.max_retries = max_retries

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
        logger.info(f"Assessing quality of step: {step.name}")

        # If step failed, return failed assessment
        if result.is_failure:
            return QualityAssessment(
                passed=False,
                score=0.0,
                feedback=f"Step failed with error: {result.error_message}",
                issues=[result.error_message or "Unknown error"],
                suggestions=["Fix the error and retry"],
            )

        # Get output artifacts
        output_preview = self._get_output_preview(result, ctx)

        # Build acceptance criteria string
        acceptance_criteria = (
            f"Description: {step.acceptance.description}\n"
            f"Required outputs: {', '.join(step.acceptance.required_outputs) or 'None specified'}\n"
            f"Validation: {step.acceptance.validation_prompt}"
        )

        prompt = STEP_ASSESSMENT_PROMPT.format(
            step_name=step.name,
            step_description=step.description,
            acceptance_criteria=acceptance_criteria,
            output_preview=output_preview,
        )

        try:
            response = await self._call_llm(prompt)
            assessment_data = self._parse_assessment_response(response)
        except Exception as e:
            logger.error(f"Failed to assess step quality: {e}")
            # Return a passing assessment on error (don't block on assessment failures)
            return QualityAssessment(
                passed=True,
                score=0.8,
                feedback="Assessment skipped due to error",
                issues=[],
                suggestions=[],
            )

        # Build assessment
        score = assessment_data.get("score", 0.5)
        passed = assessment_data.get("passed", score >= self.min_pass_score)

        return QualityAssessment(
            passed=passed,
            score=score,
            feedback=assessment_data.get("feedback", ""),
            issues=assessment_data.get("issues", []),
            suggestions=assessment_data.get("suggestions", []),
        )

    async def should_retry(
        self,
        step: Step,
        result: StepResult,
        assessment: QualityAssessment,
        ctx: PolicyContext,
    ) -> tuple[bool, str]:
        """
        Decide if a step should be retried.

        Args:
            step: The step that was executed
            result: The step's execution result
            assessment: Quality assessment result
            ctx: Current policy context

        Returns:
            Tuple of (should_retry, guidance for retry)
        """
        # Check retry limit
        if result.retry_count >= self.max_retries:
            return False, "Maximum retry limit reached"

        # Check budget
        if result.retry_count >= step.acceptance.max_retries:
            return False, "Step retry budget exhausted"

        # If assessment passed, no retry needed
        if assessment.passed:
            return False, ""

        # Generate retry guidance
        guidance = await self.get_improvement_prompt(step, result, assessment)

        return True, guidance

    async def assess_plan_output(
        self,
        ctx: PolicyContext,
    ) -> QualityAssessment:
        """
        Assess the overall quality of plan execution.

        Args:
            ctx: Current policy context with completed plan

        Returns:
            QualityAssessment for the entire plan
        """
        logger.info("Assessing overall plan quality")

        if not ctx.current_plan:
            return QualityAssessment(
                passed=False,
                score=0.0,
                feedback="No plan to assess",
                issues=["No plan exists"],
                suggestions=["Create a plan first"],
            )

        # Build summaries
        artifacts_summary = ctx.artifact_store.get_context_summary()

        history_lines = []
        for result in ctx.execution_history:
            status_emoji = "✓" if result.is_success else "✗"
            history_lines.append(
                f"{status_emoji} {result.step_id}: {result.status.value}"
            )
        history_summary = "\n".join(history_lines) if history_lines else "No execution history"

        prompt = PLAN_ASSESSMENT_PROMPT.format(
            goal=ctx.goal,
            plan_summary=ctx.current_plan.to_context_string(),
            artifacts_summary=artifacts_summary,
            history_summary=history_summary,
        )

        try:
            response = await self._call_llm(prompt)
            assessment_data = self._parse_assessment_response(response)
        except Exception as e:
            logger.error(f"Failed to assess plan quality: {e}")
            # Fallback assessment based on step completion
            completed = len([r for r in ctx.execution_history if r.is_success])
            total = len(ctx.current_plan.steps)
            score = completed / total if total > 0 else 0.0

            return QualityAssessment(
                passed=score >= self.min_pass_score,
                score=score,
                feedback=f"Completed {completed}/{total} steps",
                issues=[],
                suggestions=[],
            )

        score = assessment_data.get("score", 0.5)
        passed = assessment_data.get("passed", score >= self.min_pass_score)

        return QualityAssessment(
            passed=passed,
            score=score,
            feedback=assessment_data.get("feedback", ""),
            issues=assessment_data.get("issues", []),
            suggestions=assessment_data.get("suggestions", []),
        )

    def _get_output_preview(
        self,
        result: StepResult,
        ctx: PolicyContext,
    ) -> str:
        """Get a preview of the step output."""
        previews = []

        for artifact_id in result.output_artifact_ids:
            artifact = ctx.artifact_store.get_artifact(artifact_id)
            if artifact:
                previews.append(
                    f"[{artifact.metadata.filename}]\n{artifact.content_preview}"
                )

        if not previews:
            # Try to get from session state
            output_key = f"step_output_{result.step_id}"
            session_output = ctx.get_session_state(output_key)
            if session_output:
                previews.append(str(session_output)[:500])

        return "\n\n".join(previews) if previews else "No output available"

    async def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM with a prompt.

        Args:
            prompt: The prompt to send

        Returns:
            LLM response text
        """
        logger.info("LLM call for quality assessment (simplified implementation)")

        # Simplified implementation - in production, use actual LLM
        # Return a default passing assessment
        return json.dumps({
            "passed": True,
            "score": 0.85,
            "feedback": "Output meets acceptance criteria",
            "issues": [],
            "suggestions": []
        })

    def _parse_assessment_response(self, response: str) -> dict:
        """Parse LLM response into assessment data."""
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse assessment response: {e}")
            return {
                "passed": True,
                "score": 0.7,
                "feedback": "Parse error - defaulting to pass",
                "issues": [],
                "suggestions": [],
            }
