"""
Demo Orchestrator Agent for ADK CLI

Run with:
    adk run my_agent.demo_orchestrator
    adk web my_agent.demo_orchestrator
"""

import logging
import os
import litellm

from google.adk.models.lite_llm import LiteLlm

from .orchestrator import Orchestrator
from .policies.planning import DAGPlanner
from .policies.acting import SingleStepActor
from .policies.quality import CriticVerifier
from .policies.selection import PrioritySelector

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
    goal="Help the user with research and content creation tasks",
    planning_policy=DAGPlanner(model=MODEL, max_steps=5),
    acting_policy=SingleStepActor(model=MODEL),
    quality_policy=CriticVerifier(model=MODEL, min_pass_score=0.6),
    selection_policy=PrioritySelector(),
    max_iterations=20,
    enable_quality_gate=True,
)

logger.info(f"Demo Orchestrator initialized: {root_agent.name}")
