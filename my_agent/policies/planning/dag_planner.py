"""
DAGPlanner - LLM-based planning policy that creates DAG-structured plans.

Uses an LLM to decompose goals into steps with dependencies,
creating a directed acyclic graph of tasks.
"""

import logging
from typing import Optional, Any
import json

from .planning_policy import PlanningPolicy
from ..base_policy import PolicyContext
from ...core.plan import Plan, PlanStatus
from ...core.step import Step, StepType, StepResult, StepStatus, AcceptanceCriteria, StepBudget


logger = logging.getLogger(__name__)


# Prompt template for plan creation
PLAN_CREATION_PROMPT = """You are a planning agent. Create an execution plan to achieve the given goal.

GOAL: {goal}

CONTEXT:
{context}

Create a plan with discrete steps. Each step should:
1. Have a clear, specific objective
2. Specify what inputs it needs (artifact IDs from previous steps)
3. Specify what outputs it produces
4. List dependencies on other steps

Output your plan as JSON with this structure:
{{
  "description": "Brief description of the overall approach",
  "steps": [
    {{
      "name": "Step name",
      "description": "What this step does",
      "step_type": "gather|analyze|draft|refine|render|verify|transform|custom",
      "instruction": "Specific instruction for executing this step",
      "depends_on_indices": [0, 1],  // Indices of steps this depends on (empty for first steps)
      "priority": 1  // Higher = more important
    }}
  ]
}}

Guidelines:
- Start with information gathering steps
- Build towards the final deliverable
- Each step should be independently executable
- Keep steps focused and atomic
- Consider parallel execution where possible

Respond with ONLY valid JSON, no additional text.
"""

# Prompt template for replan decision
REPLAN_DECISION_PROMPT = """You are evaluating whether to continue with the current plan or create a new one.

CURRENT PLAN:
{plan_summary}

LAST STEP RESULT:
Step: {step_name}
Status: {step_status}
{error_info}

EXECUTION HISTORY:
{history_summary}

Should the plan be modified? Consider:
1. Can we continue with remaining steps?
2. Is the failure recoverable?
3. Do we need a fundamentally different approach?

Respond with JSON:
{{
  "should_replan": true/false,
  "reason": "Explanation of your decision"
}}

Respond with ONLY valid JSON, no additional text.
"""


class DAGPlanner(PlanningPolicy):
    """
    LLM-based planner that creates DAG-structured plans.

    Uses the provided LLM model to:
    - Decompose goals into steps
    - Determine step dependencies
    - Decide when replanning is needed
    """

    def __init__(self, model: Any, max_steps: int = 10, default_budget: Optional[StepBudget] = None):
        """
        Initialize the DAG planner.

        Args:
            model: LLM model instance (e.g., LiteLlm)
            max_steps: Maximum steps allowed in a plan
            default_budget: Default budget for steps
        """
        self.model = model
        self.max_steps = max_steps
        self.default_budget = default_budget or StepBudget()

    async def create_plan(self, ctx: PolicyContext) -> Plan:
        """
        Create a plan by asking the LLM to decompose the goal.

        Args:
            ctx: Current policy context

        Returns:
            New Plan with steps
        """
        logger.info(f"Creating plan for goal: {ctx.goal}")

        # Build context string
        context_parts = []
        if ctx.artifact_store.list_artifacts():
            context_parts.append(ctx.artifact_store.get_context_summary())
        if ctx.session_state:
            context_parts.append(f"Session state: {json.dumps(ctx.session_state, default=str)}")

        context = "\n".join(context_parts) if context_parts else "No prior context."

        prompt = PLAN_CREATION_PROMPT.format(
            goal=ctx.goal,
            context=context,
        )

        # Call LLM for plan
        try:
            response = await self._call_llm(prompt)
            plan_data = self._parse_plan_response(response)
        except Exception as e:
            logger.error(f"Failed to create plan via LLM: {e}")
            # Create a simple fallback plan
            plan_data = self._create_fallback_plan(ctx.goal)

        # Build Plan from response
        plan = Plan.create(
            goal=ctx.goal,
            description=plan_data.get("description", ""),
        )

        # Create steps with dependencies
        step_map = {}  # index -> step_id mapping
        steps_data = plan_data.get("steps", [])[:self.max_steps]

        for i, step_data in enumerate(steps_data):
            step = Step.create(
                name=step_data.get("name", f"Step {i+1}"),
                description=step_data.get("description", ""),
                step_type=self._parse_step_type(step_data.get("step_type", "custom")),
                instruction=step_data.get("instruction", ""),
                priority=step_data.get("priority", 0),
                budget=self.default_budget,
            )
            step_map[i] = step.step_id

            # Set dependencies
            dep_indices = step_data.get("depends_on_indices", [])
            step.depends_on = [
                step_map[idx] for idx in dep_indices
                if idx in step_map
            ]

            plan.add_step(step)

        # Validate the plan
        is_valid, error = plan.validate_dag()
        if not is_valid:
            logger.warning(f"Plan validation failed: {error}. Attempting to fix.")
            plan = self._fix_plan_dependencies(plan)

        plan.mark_ready()
        logger.info(f"Created plan with {len(plan.steps)} steps")

        return plan

    async def update_plan(
        self,
        ctx: PolicyContext,
        step_result: StepResult,
    ) -> Optional[Plan]:
        """
        Update plan based on step result.

        Currently returns None (no modifications).
        Future: Could add dynamic step additions.

        Args:
            ctx: Current policy context
            step_result: Result of completed step

        Returns:
            None (no plan modifications)
        """
        # Mark blocked steps if there was a failure
        if step_result.is_failure and ctx.current_plan:
            ctx.current_plan.get_blocked_steps()

        return None

    async def should_replan(
        self,
        ctx: PolicyContext,
        step_result: StepResult,
    ) -> tuple[bool, str]:
        """
        Decide if replanning is needed based on step result.

        Args:
            ctx: Current policy context
            step_result: Result of completed step

        Returns:
            Tuple of (should_replan, reason)
        """
        # Don't replan on success
        if step_result.is_success:
            return False, ""

        # Check retry count
        if step_result.retry_count < 3:
            return False, "Can retry step"

        # For failures, consult LLM
        if not ctx.current_plan:
            return True, "No current plan exists"

        step = ctx.current_plan.get_step(step_result.step_id)
        if not step:
            return False, "Step not found in plan"

        # Build prompt for replan decision
        error_info = f"Error: {step_result.error_message}" if step_result.error_message else ""

        history_lines = []
        for r in ctx.execution_history[-5:]:  # Last 5 results
            history_lines.append(f"- {r.step_id}: {r.status.value}")
        history_summary = "\n".join(history_lines) if history_lines else "No history"

        prompt = REPLAN_DECISION_PROMPT.format(
            plan_summary=ctx.current_plan.to_context_string(),
            step_name=step.name,
            step_status=step_result.status.value,
            error_info=error_info,
            history_summary=history_summary,
        )

        try:
            response = await self._call_llm(prompt)
            data = json.loads(response)
            return data.get("should_replan", False), data.get("reason", "")
        except Exception as e:
            logger.warning(f"Failed to get replan decision: {e}")
            # Default: don't replan on parse errors
            return False, f"Error getting decision: {e}"

    async def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM with a prompt.

        Args:
            prompt: The prompt to send

        Returns:
            LLM response text
        """
        # This is a simplified implementation
        # In practice, you'd use the ADK's LLM calling mechanism
        from google.genai import types

        # Create a simple content request
        content = types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )

        # For now, return a mock response
        # In real implementation, you'd call self.model
        logger.info("LLM call for planning (simplified implementation)")

        # Return a default plan structure
        return json.dumps({
            "description": "Default plan structure",
            "steps": [
                {
                    "name": "Gather Information",
                    "description": "Collect necessary information for the task",
                    "step_type": "gather",
                    "instruction": "Gather all relevant information",
                    "depends_on_indices": [],
                    "priority": 2
                },
                {
                    "name": "Process and Analyze",
                    "description": "Process the gathered information",
                    "step_type": "analyze",
                    "instruction": "Analyze the gathered information",
                    "depends_on_indices": [0],
                    "priority": 1
                },
                {
                    "name": "Generate Output",
                    "description": "Create the final output",
                    "step_type": "draft",
                    "instruction": "Generate the final deliverable",
                    "depends_on_indices": [1],
                    "priority": 0
                }
            ]
        })

    def _parse_plan_response(self, response: str) -> dict:
        """Parse LLM response into plan data."""
        try:
            # Try to extract JSON from response
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan response: {e}")
            return {"description": "Parse error", "steps": []}

    def _parse_step_type(self, type_str: str) -> StepType:
        """Parse step type string to enum."""
        type_map = {
            "gather": StepType.GATHER,
            "analyze": StepType.ANALYZE,
            "draft": StepType.DRAFT,
            "refine": StepType.REFINE,
            "render": StepType.RENDER,
            "verify": StepType.VERIFY,
            "transform": StepType.TRANSFORM,
            "custom": StepType.CUSTOM,
        }
        return type_map.get(type_str.lower(), StepType.CUSTOM)

    def _create_fallback_plan(self, goal: str) -> dict:
        """Create a simple fallback plan."""
        return {
            "description": f"Simple plan for: {goal}",
            "steps": [
                {
                    "name": "Execute Task",
                    "description": goal,
                    "step_type": "custom",
                    "instruction": goal,
                    "depends_on_indices": [],
                    "priority": 0
                }
            ]
        }

    def _fix_plan_dependencies(self, plan: Plan) -> Plan:
        """Fix invalid dependencies in a plan."""
        valid_ids = {s.step_id for s in plan.steps}

        for step in plan.steps:
            step.depends_on = [
                dep_id for dep_id in step.depends_on
                if dep_id in valid_ids
            ]

        return plan
