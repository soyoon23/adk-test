# ADK 3-Layer Agent Architecture

A flexible, extensible agent framework built on Google ADK (Agent Development Kit) for long-horizon tasks with Plan-Act-Replan capabilities.

## Overview

This framework implements a 3-layer architecture designed for:

- **Long-horizon tasks**: Complex workflows that require planning, execution, and adaptive replanning
- **Universal artifacts**: Support for documents, JSON, images, code, and binary outputs
- **Pluggable patterns**: Easily swap planning, execution, and quality assessment strategies

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 3: Orchestrator                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              State Machine (Plan-Act-Replan)            │   │
│  │  INIT → PLAN → SELECT → EXECUTE → REFLECT → QUALITY →  │   │
│  │                    ↑                    │               │   │
│  │                    └── REPLAN ←─────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                     Layer 2: Policies                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐       │
│  │ Planning │ │  Acting  │ │ Quality  │ │  Selection   │       │
│  │  Policy  │ │  Policy  │ │  Policy  │ │    Policy    │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘       │
├─────────────────────────────────────────────────────────────────┤
│                   Layer 1: Core Models                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐       │
│  │ Artifact │ │   Step   │ │   Plan   │ │ ArtifactStore│       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 1: Core (Immutable Data Models)

| Component | Description |
|-----------|-------------|
| `Artifact` | Universal output container (text, JSON, images, code) with metadata and content preview |
| `ArtifactStore` | Storage abstraction - LLM sees only artifact IDs, not full content (prevents context explosion) |
| `Step` | Task unit with type, acceptance criteria, budget constraints, and DAG dependencies |
| `Plan` | Collection of Steps forming a DAG with validation and progress tracking |

### Layer 2: Policies (Pluggable Decision-Making)

| Policy | Responsibility | Default Implementation |
|--------|----------------|----------------------|
| `PlanningPolicy` | Create/update execution plans | `DAGPlanner` - LLM-based plan decomposition |
| `ActingPolicy` | Execute individual steps | `SingleStepActor` - Sequential step execution |
| `QualityPolicy` | Assess output quality | `CriticVerifier` - LLM-based quality scoring |
| `SelectionPolicy` | Choose next step to execute | `PrioritySelector` - Priority-based selection |

### Layer 3: Orchestrator (State Machine)

The `Orchestrator` coordinates all policies without making decisions itself:

1. **PLANNING**: Creates execution plan via `PlanningPolicy`
2. **SELECTING**: Chooses next step via `SelectionPolicy`
3. **EXECUTING**: Runs step via `ActingPolicy`
4. **REFLECTING**: Checks if replanning needed via `PlanningPolicy`
5. **QUALITY_GATE**: Assesses output via `QualityPolicy`
6. **REPLANNING**: Creates new plan if needed

## Requirements

- Python 3.11+
- [Ollama](https://ollama.ai/) (for local LLM)
- [uv](https://github.com/astral-sh/uv) (package manager, recommended)

## Installation

```bash
# Clone the repository
git clone https://github.com/soyoon23/adk-test.git
cd adk-test

# Create virtual environment and install dependencies
uv sync

# Or with pip
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

## LiteLLM Proxy Setup

To use local Ollama models with ADK:

```bash
# Download model via Ollama
ollama pull qwen:7b

# Start LiteLLM proxy
cd litellm-proxy
./start_proxy.sh

# Or manually
litellm --config litellm_config.yaml
```

The proxy runs at `http://localhost:4000` by default.

## Quick Start

### Basic Usage with Orchestrator

```python
import asyncio
from my_agent import (
    Orchestrator,
    DAGPlanner,
    SingleStepActor,
    CriticVerifier,
    PrioritySelector,
)
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

# Configure model (using LiteLLM proxy)
model = LiteLlm(model="qwen:7b")

# Create orchestrator with all policies
orchestrator = Orchestrator(
    name="ResearchAgent",
    goal="Write a summary of recent AI trends",
    planning_policy=DAGPlanner(model=model),
    acting_policy=SingleStepActor(model=model),
    quality_policy=CriticVerifier(model=model),
    selection_policy=PrioritySelector(),
)

# Run with ADK Runner
async def main():
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="my_app",
        user_id="user1",
        session_id="session1",
    )

    runner = Runner(
        agent=orchestrator,
        app_name="my_app",
        session_service=session_service,
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text="Start the research task")]
    )

    async for event in runner.run_async(
        user_id="user1",
        session_id="session1",
        new_message=message,
    ):
        print(f"[{event.author}] {event}")

asyncio.run(main())
```

### Using Core Components Directly

```python
from my_agent import (
    ArtifactStore,
    ArtifactType,
    Step,
    StepType,
    Plan,
)

# Create artifact store
store = ArtifactStore()

# Save an artifact
artifact_id = store.save(
    content="# Research Report\n\nAI is transforming...",
    artifact_type=ArtifactType.DOCUMENT,
    filename="report.md",
    description="AI trends research report",
    created_by_step_id="step-001",
    tags=["research", "ai"],
)

# Create steps with dependencies
gather_step = Step.create(
    name="Gather Information",
    description="Collect data from various sources",
    step_type=StepType.GATHER,
    instruction="Search for recent AI news and papers",
    priority=2,
)

analyze_step = Step.create(
    name="Analyze Data",
    description="Analyze collected information",
    step_type=StepType.ANALYZE,
    instruction="Identify key trends and patterns",
    depends_on=[gather_step.step_id],
    priority=1,
)

# Create plan
plan = Plan.create(
    goal="Research AI trends",
    steps=[gather_step, analyze_step],
)

# Check ready steps (steps with no unmet dependencies)
ready = plan.get_ready_steps()
print(f"Ready to execute: {[s.name for s in ready]}")
```

### Running the Original StoryFlow Agent

The original `StoryFlowAgent` is preserved for reference:

```bash
uv run python my_agent/agent.py
```

**StoryFlow Workflow:**
```
StoryGenerator → CriticReviser Loop (2x) → PostProcessing → Tone Check
                                                              ↓
                                               Negative? → Regenerate
```

## Project Structure

```
adk-test/
├── my_agent/
│   ├── __init__.py                    # Main exports
│   ├── agent.py                       # Original StoryFlowAgent (reference)
│   │
│   ├── core/                          # Layer 1 - Data Models
│   │   ├── artifact.py                # Artifact, ArtifactMetadata, ArtifactType
│   │   ├── artifact_store.py          # ArtifactStore
│   │   ├── step.py                    # Step, StepResult, AcceptanceCriteria
│   │   └── plan.py                    # Plan, PlanStatus
│   │
│   ├── policies/                      # Layer 2 - Decision Policies
│   │   ├── base_policy.py             # PolicyContext
│   │   ├── planning/
│   │   │   ├── planning_policy.py     # Abstract interface
│   │   │   └── dag_planner.py         # DAGPlanner implementation
│   │   ├── acting/
│   │   │   ├── acting_policy.py       # Abstract interface
│   │   │   └── single_step_actor.py   # SingleStepActor implementation
│   │   ├── quality/
│   │   │   ├── quality_policy.py      # Abstract interface
│   │   │   └── critic_verifier.py     # CriticVerifier implementation
│   │   └── selection/
│   │       ├── selection_policy.py    # Abstract interface
│   │       └── priority_selector.py   # PrioritySelector implementation
│   │
│   ├── orchestrator/                  # Layer 3 - State Machine
│   │   ├── orchestrator_state.py      # OrchestratorState, OrchestratorPhase
│   │   └── orchestrator.py            # Orchestrator (BaseAgent)
│   │
│   └── callbacks/
│       └── system_prompt_override.py  # Dynamic instruction callbacks
│
├── litellm-proxy/
│   ├── litellm_config.yaml            # Proxy configuration
│   ├── start_proxy.sh                 # Start script
│   └── stop_proxy.sh                  # Stop script
│
├── pyproject.toml
└── README.md
```

## Configuration

### Environment Variables

Create `my_agent/.env`:

```env
LITELLM_PROXY_API_BASE=http://localhost:4000
LITELLM_PROXY_API_KEY=sk-1234
GOOGLE_API_KEY=your_api_key_here  # If using Google models
```

### Orchestrator Options

| Option | Default | Description |
|--------|---------|-------------|
| `max_iterations` | 50 | Maximum orchestrator loop iterations |
| `enable_quality_gate` | True | Run quality assessment after steps |

### Step Budget Defaults

| Option | Default | Description |
|--------|---------|-------------|
| `max_tool_calls` | 10 | Max tool calls per step |
| `max_llm_calls` | 5 | Max LLM invocations per step |
| `timeout_seconds` | 300 | Step execution timeout |

## Design Principles

1. **Separation of Concerns**: Core data models, policies, and orchestration are independent layers
2. **Policy Delegation**: Orchestrator makes no decisions - all logic lives in pluggable policies
3. **Context Explosion Prevention**: LLM sees artifact IDs and previews, not full content
4. **Checkpointing**: OrchestratorState supports serialization for pause/resume
5. **DAG Validation**: Plans validate for cycles and missing dependencies before execution

## Creating Custom Policies

### Custom Planning Policy

```python
from my_agent.policies.planning import PlanningPolicy
from my_agent import Plan, Step, StepType, PolicyContext

class MyCustomPlanner(PlanningPolicy):
    async def create_plan(self, ctx: PolicyContext) -> Plan:
        steps = [
            Step.create(name="Step 1", description="...", step_type=StepType.GATHER),
            Step.create(name="Step 2", description="...", step_type=StepType.DRAFT),
        ]
        steps[1].depends_on = [steps[0].step_id]

        plan = Plan.create(goal=ctx.goal, steps=steps)
        plan.mark_ready()
        return plan

    async def update_plan(self, ctx, step_result):
        return None

    async def should_replan(self, ctx, step_result):
        return False, ""
```

### Custom Quality Policy

```python
from my_agent.policies.quality import QualityPolicy, QualityAssessment

class StrictVerifier(QualityPolicy):
    async def assess_step_output(self, step, result, ctx) -> QualityAssessment:
        # Custom assessment logic
        return QualityAssessment(
            passed=True,
            score=0.95,
            feedback="Excellent output",
            issues=[],
            suggestions=[],
        )

    async def should_retry(self, step, result, assessment, ctx):
        return assessment.score < 0.8, "Score below threshold"

    async def assess_plan_output(self, ctx) -> QualityAssessment:
        # Assess overall plan completion
        ...
```

## API Reference

### Core Models

- `Artifact` - Content with metadata, preview, and hash
- `ArtifactStore` - Save/load/query artifacts by ID
- `Step` - Task unit with type, budget, acceptance criteria
- `Plan` - DAG of steps with validation

### Enums

- `ArtifactType`: TEXT, DOCUMENT, JSON, CSV, IMAGE, CODE, BINARY
- `StepType`: GATHER, ANALYZE, DRAFT, REFINE, RENDER, VERIFY, TRANSFORM, CUSTOM
- `StepStatus`: PENDING, READY, IN_PROGRESS, COMPLETED, FAILED, SKIPPED, BLOCKED
- `PlanStatus`: DRAFT, READY, IN_PROGRESS, COMPLETED, FAILED, REPLANNING, CANCELLED
- `OrchestratorPhase`: INITIALIZING, PLANNING, SELECTING, EXECUTING, REFLECTING, QUALITY_GATE, REPLANNING, COMPLETED, FAILED, PAUSED

## License

Apache License 2.0

## Acknowledgments

Built on [Google ADK (Agent Development Kit)](https://github.com/google/adk-python)
