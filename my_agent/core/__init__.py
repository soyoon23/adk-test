"""
Core Layer - Immutable data models and stores.

This layer contains the foundational data structures for the agent architecture:
- Artifact: Data model for agent outputs (documents, JSON, images, code, etc.)
- ArtifactStore: Storage abstraction for artifacts
- Step: Task unit schema with acceptance criteria and budget
- Plan: DAG of steps with dependency management
"""

from .artifact import Artifact, ArtifactMetadata, ArtifactType
from .artifact_store import ArtifactStore
from .step import (
    Step,
    StepType,
    StepStatus,
    StepResult,
    AcceptanceCriteria,
    StepBudget,
)
from .plan import Plan, PlanStatus

__all__ = [
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
]
