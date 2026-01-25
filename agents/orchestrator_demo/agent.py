"""
Orchestrator Demo - 3-Layer Agent Architecture

This demonstrates the Plan-Act-Replan loop:
    INIT → PLAN → SELECT → EXECUTE → REFLECT → QUALITY_GATE → COMPLETE
                     ↑                    │
                     └── REPLAN ←─────────┘
"""

import logging
import os
import litellm
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.adk.models.lite_llm import LiteLlm

from my_agent.orchestrator import Orchestrator
from my_agent.policies.planning import DAGPlanner
from my_agent.policies.acting import SingleStepActor
from my_agent.policies.quality import CriticVerifier
from my_agent.policies.selection import PrioritySelector

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- LiteLLM Proxy Configuration ---
os.environ["LITELLM_PROXY_API_BASE"] = "http://localhost:4000"
os.environ["LITELLM_PROXY_API_KEY"] = "sk-1234"
litellm.use_litellm_proxy = True

# --- Model Configuration ---
MODEL = LiteLlm(model="qwen:7b")

# --- Create the Orchestrator Agent ---
root_agent = Orchestrator(
    name="ResearchOrchestrator",
    goal="Help users with research and content creation using Plan-Act-Replan",
    planning_policy=DAGPlanner(model=MODEL, max_steps=5),
    acting_policy=SingleStepActor(model=MODEL),
    quality_policy=CriticVerifier(model=MODEL, min_pass_score=0.6),
    selection_policy=PrioritySelector(),
    max_iterations=20,
    enable_quality_gate=True,
)

logger.info(f"Orchestrator Demo initialized: {root_agent.name}")
