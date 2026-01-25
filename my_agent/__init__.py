"""
ADK 3-Layer Agent Architecture

A flexible, extensible agent framework built on Google ADK with:
- Core layer: Immutable data models (Artifact, Step, Plan)
- Policy layer: Pluggable decision-making (Planning, Acting, Quality, Selection)
- Orchestrator layer: State machine for long-horizon tasks

Usage:
    from my_agent.orchestrator import Orchestrator
    from my_agent.policies.planning import DAGPlanner
    from my_agent.policies.acting import SingleStepActor
    from my_agent.policies.quality import CriticVerifier
    from my_agent.policies.selection import PrioritySelector
    from google.adk.models.lite_llm import LiteLlm

    model = LiteLlm(model="qwen:7b")

    orchestrator = Orchestrator(
        name="ResearchAgent",
        goal="AI trend research report",
        planning_policy=DAGPlanner(model=model),
        acting_policy=SingleStepActor(model=model),
        quality_policy=CriticVerifier(model=model),
        selection_policy=PrioritySelector(),
    )
"""

# Core layer exports
from .core import (
    Artifact,
    ArtifactMetadata,
    ArtifactType,
    ArtifactStore,
    Step,
    StepType,
    StepStatus,
    StepResult,
    AcceptanceCriteria,
    StepBudget,
    Plan,
    PlanStatus,
)

# Policy layer exports
from .policies import PolicyContext
from .policies.planning import PlanningPolicy, DAGPlanner
from .policies.acting import ActingPolicy, SingleStepActor
from .policies.quality import QualityPolicy, QualityAssessment, CriticVerifier
from .policies.selection import SelectionPolicy, PrioritySelector

# Orchestrator layer exports
from .orchestrator import Orchestrator, OrchestratorState, OrchestratorPhase

# Callback exports
from .callbacks import create_system_prompt_override, create_step_instruction_provider

# Keep existing agent for reference
from . import agent

__all__ = [
    # Core
    "Artifact",
    "ArtifactMetadata",
    "ArtifactType",
    "ArtifactStore",
    "Step",
    "StepType",
    "StepStatus",
    "StepResult",
    "AcceptanceCriteria",
    "StepBudget",
    "Plan",
    "PlanStatus",
    # Policies
    "PolicyContext",
    "PlanningPolicy",
    "DAGPlanner",
    "ActingPolicy",
    "SingleStepActor",
    "QualityPolicy",
    "QualityAssessment",
    "CriticVerifier",
    "SelectionPolicy",
    "PrioritySelector",
    # Orchestrator
    "Orchestrator",
    "OrchestratorState",
    "OrchestratorPhase",
    # Callbacks
    "create_system_prompt_override",
    "create_step_instruction_provider",
    # Legacy
    "agent",
]
