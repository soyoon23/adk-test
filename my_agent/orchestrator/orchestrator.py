"""
Orchestrator - Main agent implementing the Plan-Act-Replan loop.

The Orchestrator is a BaseAgent that:
- Coordinates planning, acting, quality, and selection policies
- Implements the state machine for long-horizon tasks
- Delegates all decisions to policies (no embedded logic)
"""

import logging
from typing import AsyncGenerator, Optional, Any

from typing_extensions import override
from pydantic import Field

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from .orchestrator_state import OrchestratorState, OrchestratorPhase
from ..policies.base_policy import PolicyContext
from ..policies.planning.planning_policy import PlanningPolicy
from ..policies.acting.acting_policy import ActingPolicy
from ..policies.quality.quality_policy import QualityPolicy
from ..policies.selection.selection_policy import SelectionPolicy
from ..core.step import StepStatus


logger = logging.getLogger(__name__)


class Orchestrator(BaseAgent):
    """
    Main orchestrator agent implementing the Plan-Act-Replan loop.

    State Machine:
        INITIALIZING → PLANNING → SELECTING → EXECUTING → REFLECTING → QUALITY_GATE → COMPLETED
                          ↑           ↑                         │
                          └───────────┴── REPLANNING ←──────────┘

    Key principle: The orchestrator does NOT make decisions.
    All decisions are delegated to the appropriate policy.
    """

    model_config = {"arbitrary_types_allowed": True}

    # Goal
    goal: str = Field(
        description="The high-level goal to achieve"
    )

    # Policies
    planning_policy: PlanningPolicy = Field(
        description="Policy for creating and updating plans"
    )
    acting_policy: ActingPolicy = Field(
        description="Policy for executing steps"
    )
    quality_policy: QualityPolicy = Field(
        description="Policy for assessing quality"
    )
    selection_policy: SelectionPolicy = Field(
        description="Policy for selecting next steps"
    )

    # Configuration
    max_iterations: int = Field(
        default=50,
        ge=1,
        description="Maximum orchestrator iterations"
    )
    enable_quality_gate: bool = Field(
        default=True,
        description="Whether to run quality assessment on outputs"
    )

    # Internal state (not persisted in constructor)
    _state: Optional[OrchestratorState] = None
    _policy_context: Optional[PolicyContext] = None

    def __init__(
        self,
        name: str,
        goal: str,
        planning_policy: PlanningPolicy,
        acting_policy: ActingPolicy,
        quality_policy: QualityPolicy,
        selection_policy: SelectionPolicy,
        max_iterations: int = 50,
        enable_quality_gate: bool = True,
        **kwargs
    ):
        """
        Initialize the orchestrator.

        Args:
            name: Agent name
            goal: High-level goal to achieve
            planning_policy: Policy for plan creation/update
            acting_policy: Policy for step execution
            quality_policy: Policy for quality assessment
            selection_policy: Policy for step selection
            max_iterations: Maximum iterations
            enable_quality_gate: Enable quality checks
        """
        super().__init__(
            name=name,
            goal=goal,
            planning_policy=planning_policy,
            acting_policy=acting_policy,
            quality_policy=quality_policy,
            selection_policy=selection_policy,
            max_iterations=max_iterations,
            enable_quality_gate=enable_quality_gate,
            **kwargs
        )

    @override
    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """
        Main orchestrator loop implementing the state machine.

        Args:
            ctx: ADK invocation context

        Yields:
            Events from orchestration
        """
        logger.info(f"[{self.name}] Starting orchestration for goal: {self.goal}")

        # Initialize state
        self._state = OrchestratorState.create(
            goal=self.goal,
            max_iterations=self.max_iterations,
            session_state=dict(ctx.session.state) if ctx.session else {},
        )

        # Initialize policy context
        self._policy_context = PolicyContext(
            goal=self.goal,
            artifact_store=self._state.artifact_store,
            session_state=self._state.session_state,
            max_iterations=self.max_iterations,
        )

        # Yield initialization event
        yield self._create_event(
            "orchestrator_started",
            {"goal": self.goal, "execution_id": self._state.execution_id}
        )

        # Main state machine loop
        while self._state.can_continue():
            self._state.increment_iteration()
            logger.info(
                f"[{self.name}] Iteration {self._state.iteration}, "
                f"Phase: {self._state.phase.value}"
            )

            try:
                async for event in self._execute_phase(ctx):
                    yield event

            except Exception as e:
                logger.error(f"[{self.name}] Error in phase {self._state.phase}: {e}")
                self._state.record_error(str(e))

                if self._state.error_count > 3:
                    self._state.transition_to(OrchestratorPhase.FAILED)
                    yield self._create_event(
                        "orchestrator_failed",
                        {"error": str(e), "phase": self._state.phase.value}
                    )
                    break

        # Final state
        if self._state.phase == OrchestratorPhase.COMPLETED:
            logger.info(f"[{self.name}] Orchestration completed successfully")
            yield self._create_event(
                "orchestrator_completed",
                self._state.get_progress()
            )
        elif self._state.is_max_iterations_reached():
            logger.warning(f"[{self.name}] Max iterations reached")
            self._state.transition_to(OrchestratorPhase.FAILED)
            yield self._create_event(
                "orchestrator_max_iterations",
                self._state.get_progress()
            )

    async def _execute_phase(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """
        Execute the current phase of the state machine.

        Args:
            ctx: ADK invocation context

        Yields:
            Events from phase execution
        """
        phase = self._state.phase

        if phase == OrchestratorPhase.INITIALIZING:
            async for event in self._phase_initializing(ctx):
                yield event

        elif phase == OrchestratorPhase.PLANNING:
            async for event in self._phase_planning(ctx):
                yield event

        elif phase == OrchestratorPhase.SELECTING:
            async for event in self._phase_selecting(ctx):
                yield event

        elif phase == OrchestratorPhase.EXECUTING:
            async for event in self._phase_executing(ctx):
                yield event

        elif phase == OrchestratorPhase.REFLECTING:
            async for event in self._phase_reflecting(ctx):
                yield event

        elif phase == OrchestratorPhase.QUALITY_GATE:
            async for event in self._phase_quality_gate(ctx):
                yield event

        elif phase == OrchestratorPhase.REPLANNING:
            async for event in self._phase_replanning(ctx):
                yield event

    async def _phase_initializing(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Initialize and transition to planning."""
        logger.info(f"[{self.name}] Initializing...")

        # Transition to planning
        self._state.transition_to(OrchestratorPhase.PLANNING)

        yield self._create_event("phase_transition", {"to": "planning"})

    async def _phase_planning(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Create or update the execution plan."""
        logger.info(f"[{self.name}] Planning...")

        # Delegate to planning policy
        plan = await self.planning_policy.create_plan(self._policy_context)

        # Validate plan
        is_valid, error = await self.planning_policy.validate_plan(plan)
        if not is_valid:
            logger.error(f"[{self.name}] Plan validation failed: {error}")
            self._state.record_error(f"Invalid plan: {error}")
            yield self._create_event("plan_invalid", {"error": error})
            return

        # Store plan
        self._state.set_plan(plan)
        self._policy_context.current_plan = plan

        logger.info(f"[{self.name}] Created plan with {len(plan.steps)} steps")

        yield self._create_event(
            "plan_created",
            {
                "plan_id": plan.plan_id,
                "num_steps": len(plan.steps),
                "steps": [s.name for s in plan.steps],
            }
        )

        # Transition to selecting
        self._state.transition_to(OrchestratorPhase.SELECTING)

    async def _phase_selecting(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Select the next step to execute."""
        logger.info(f"[{self.name}] Selecting next step...")

        if not self._state.current_plan:
            self._state.transition_to(OrchestratorPhase.PLANNING)
            return

        # Get ready steps
        ready_steps = self._state.current_plan.get_ready_steps()

        if not ready_steps:
            # Check if plan is complete
            if self._state.current_plan.is_complete():
                logger.info(f"[{self.name}] All steps completed")
                self._state.transition_to(OrchestratorPhase.QUALITY_GATE)
            elif self._state.current_plan.has_failures():
                logger.warning(f"[{self.name}] Plan has failures, no ready steps")
                self._state.transition_to(OrchestratorPhase.REPLANNING)
            else:
                # Stuck - no ready steps but not complete
                logger.error(f"[{self.name}] No ready steps available")
                self._state.transition_to(OrchestratorPhase.FAILED)
            return

        # Delegate selection to policy
        selected_step = await self.selection_policy.select_next_step(
            ready_steps,
            self._policy_context,
        )

        if not selected_step:
            logger.warning(f"[{self.name}] No step selected")
            self._state.transition_to(OrchestratorPhase.QUALITY_GATE)
            return

        self._state.set_current_step(selected_step.step_id)

        yield self._create_event(
            "step_selected",
            {"step_id": selected_step.step_id, "step_name": selected_step.name}
        )

        # Transition to executing
        self._state.transition_to(OrchestratorPhase.EXECUTING)

    async def _phase_executing(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Execute the current step."""
        if not self._state.current_step_id or not self._state.current_plan:
            self._state.transition_to(OrchestratorPhase.SELECTING)
            return

        step = self._state.current_plan.get_step(self._state.current_step_id)
        if not step:
            logger.error(f"[{self.name}] Step not found: {self._state.current_step_id}")
            self._state.transition_to(OrchestratorPhase.SELECTING)
            return

        logger.info(f"[{self.name}] Executing step: {step.name}")

        yield self._create_event(
            "step_started",
            {"step_id": step.step_id, "step_name": step.name}
        )

        # Delegate execution to acting policy
        async for event in self.acting_policy.execute_step(
            step,
            self._policy_context,
            ctx,
        ):
            # Pass through events
            if isinstance(event, dict):
                yield self._create_event(event.get("type", "step_event"), event)
            else:
                yield event

        # Get result
        result = await self.acting_policy.get_step_result(step, self._policy_context)

        # Record result
        self._state.add_step_result(result)
        self._policy_context.add_result(result)

        yield self._create_event(
            "step_completed" if result.is_success else "step_failed",
            {
                "step_id": step.step_id,
                "status": result.status.value,
                "artifacts": result.output_artifact_ids,
            }
        )

        # Quality assessment if enabled
        if self.enable_quality_gate and result.is_success:
            assessment = await self.quality_policy.assess_step_output(
                step,
                result,
                self._policy_context,
            )

            if not assessment.passed:
                should_retry, guidance = await self.quality_policy.should_retry(
                    step,
                    result,
                    assessment,
                    self._policy_context,
                )

                if should_retry:
                    # Reset step for retry
                    step.status = StepStatus.PENDING
                    result.retry_count += 1
                    yield self._create_event(
                        "step_retry",
                        {"step_id": step.step_id, "guidance": guidance}
                    )
                    self._state.transition_to(OrchestratorPhase.SELECTING)
                    return

        # Clear current step
        self._state.set_current_step(None)

        # Transition to reflecting
        self._state.transition_to(OrchestratorPhase.REFLECTING)

    async def _phase_reflecting(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Reflect on progress and decide next action."""
        logger.info(f"[{self.name}] Reflecting...")

        last_result = self._policy_context.get_last_result()
        if not last_result:
            self._state.transition_to(OrchestratorPhase.SELECTING)
            return

        # Check if replanning is needed
        should_replan, reason = await self.planning_policy.should_replan(
            self._policy_context,
            last_result,
        )

        if should_replan:
            logger.info(f"[{self.name}] Replanning: {reason}")
            yield self._create_event("replan_triggered", {"reason": reason})
            self._state.transition_to(OrchestratorPhase.REPLANNING)
        else:
            # Continue with current plan
            self._state.transition_to(OrchestratorPhase.SELECTING)

    async def _phase_quality_gate(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Final quality assessment of plan output."""
        logger.info(f"[{self.name}] Quality gate...")

        if not self.enable_quality_gate:
            self._state.transition_to(OrchestratorPhase.COMPLETED)
            return

        # Assess overall plan quality
        assessment = await self.quality_policy.assess_plan_output(self._policy_context)

        yield self._create_event(
            "quality_assessment",
            {
                "passed": assessment.passed,
                "score": assessment.score,
                "feedback": assessment.feedback,
            }
        )

        if assessment.passed:
            self._state.transition_to(OrchestratorPhase.COMPLETED)
        else:
            # Consider replanning for quality improvement
            if self._state.iteration < self.max_iterations - 5:
                yield self._create_event(
                    "quality_improvement_needed",
                    {"suggestions": assessment.suggestions}
                )
                self._state.transition_to(OrchestratorPhase.REPLANNING)
            else:
                # Accept current quality due to iteration limit
                logger.warning(f"[{self.name}] Accepting below-threshold quality")
                self._state.transition_to(OrchestratorPhase.COMPLETED)

    async def _phase_replanning(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Create a new plan based on current state."""
        logger.info(f"[{self.name}] Replanning...")

        # Mark current plan as replanning
        if self._state.current_plan:
            self._state.current_plan.mark_replanning()

        # Transition back to planning
        self._state.transition_to(OrchestratorPhase.PLANNING)

        yield self._create_event("replanning_started", {})

    def _create_event(self, event_type: str, data: dict) -> Event:
        """Create an event with the given type and data."""
        from google.genai import types

        # Create event content
        content = types.Content(
            role="model",
            parts=[types.Part(text=f"[{event_type}] {data}")]
        )

        # Create and return event
        return Event(
            author=self.name,
            content=content,
        )

    def get_state(self) -> Optional[OrchestratorState]:
        """Get the current orchestrator state."""
        return self._state

    def get_progress(self) -> dict:
        """Get current progress information."""
        if self._state:
            return self._state.get_progress()
        return {}
