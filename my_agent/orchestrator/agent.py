"""
Orchestrator Demo Agent for ADK Web UI

This file exports root_agent for ADK CLI compatibility.
Access via: http://127.0.0.1:8000 -> Select 'orchestrator' app
"""

import logging
import os
import litellm

from google.adk.models.lite_llm import LiteLlm

from .orchestrator import Orchestrator
from ..policies.planning import DAGPlanner
from ..policies.acting import SingleStepActor
from ..policies.quality import CriticVerifier
from ..policies.selection import PrioritySelector

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
    goal="Help the user with research and content creation tasks using Plan-Act-Replan loop",
    planning_policy=DAGPlanner(model=MODEL, max_steps=5),
    acting_policy=SingleStepActor(model=MODEL),
    quality_policy=CriticVerifier(model=MODEL, min_pass_score=0.6),
    selection_policy=PrioritySelector(),
    max_iterations=20,
    enable_quality_gate=True,
)

logger.info(f"Orchestrator Agent initialized: {root_agent.name}")
