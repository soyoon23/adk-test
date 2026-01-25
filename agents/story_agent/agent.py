"""
StoryFlowAgent - Multi-agent story generation workflow

Workflow:
    StoryGenerator → CriticReviser Loop (2x) → PostProcessing → Tone Check
                                                                  ↓
                                                   Negative? → Regenerate
"""

import logging
import os
import litellm

from typing import AsyncGenerator
from typing_extensions import override

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- LiteLLM Proxy Configuration ---
os.environ["LITELLM_PROXY_API_BASE"] = "http://localhost:4000"
os.environ["LITELLM_PROXY_API_KEY"] = "sk-1234"
litellm.use_litellm_proxy = True

# --- Model Configuration ---
MODEL = LiteLlm(model="qwen:7b")


class StoryFlowAgent(BaseAgent):
    """Custom agent for story generation and refinement workflow."""

    story_generator: LlmAgent
    critic: LlmAgent
    reviser: LlmAgent
    grammar_check: LlmAgent
    tone_check: LlmAgent
    loop_agent: LoopAgent
    sequential_agent: SequentialAgent

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        story_generator: LlmAgent,
        critic: LlmAgent,
        reviser: LlmAgent,
        grammar_check: LlmAgent,
        tone_check: LlmAgent,
    ):
        loop_agent = LoopAgent(
            name="CriticReviserLoop", sub_agents=[critic, reviser], max_iterations=2
        )
        sequential_agent = SequentialAgent(
            name="PostProcessing", sub_agents=[grammar_check, tone_check]
        )

        sub_agents_list = [story_generator, loop_agent, sequential_agent]

        super().__init__(
            name=name,
            story_generator=story_generator,
            critic=critic,
            reviser=reviser,
            grammar_check=grammar_check,
            tone_check=tone_check,
            loop_agent=loop_agent,
            sequential_agent=sequential_agent,
            sub_agents=sub_agents_list,
        )

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        logger.info(f"[{self.name}] Starting story generation workflow.")

        # 1. Initial Story Generation
        logger.info(f"[{self.name}] Running StoryGenerator...")
        async for event in self.story_generator.run_async(ctx):
            yield event

        if "current_story" not in ctx.session.state or not ctx.session.state["current_story"]:
            logger.error(f"[{self.name}] Failed to generate initial story.")
            return

        # 2. Critic-Reviser Loop
        logger.info(f"[{self.name}] Running CriticReviserLoop...")
        async for event in self.loop_agent.run_async(ctx):
            yield event

        # 3. Sequential Post-Processing
        logger.info(f"[{self.name}] Running PostProcessing...")
        async for event in self.sequential_agent.run_async(ctx):
            yield event

        # 4. Tone-Based Conditional Logic
        tone_check_result = ctx.session.state.get("tone_check_result")
        if tone_check_result == "negative":
            logger.info(f"[{self.name}] Tone is negative. Regenerating story...")
            async for event in self.story_generator.run_async(ctx):
                yield event

        logger.info(f"[{self.name}] Workflow finished.")


# --- Define individual LLM agents ---
story_generator = LlmAgent(
    name="StoryGenerator",
    model=MODEL,
    instruction="""You are a story writer. Write a short story (around 100 words) based on the user's request.
If no specific topic is given, write about "a brave kitten exploring a haunted house".""",
    output_key="current_story",
)

critic = LlmAgent(
    name="Critic",
    model=MODEL,
    instruction="""You are a story critic. Review the story: {{current_story}}
Provide 1-2 sentences of constructive criticism on plot or character.""",
    output_key="criticism",
)

reviser = LlmAgent(
    name="Reviser",
    model=MODEL,
    instruction="""You are a story reviser. Revise the story: {{current_story}}
Based on this criticism: {{criticism}}
Output only the revised story.""",
    output_key="current_story",
)

grammar_check = LlmAgent(
    name="GrammarCheck",
    model=MODEL,
    instruction="""Check the grammar of: {{current_story}}
Output corrections as a list, or 'Grammar is good!' if no errors.""",
    output_key="grammar_suggestions",
)

tone_check = LlmAgent(
    name="ToneCheck",
    model=MODEL,
    instruction="""Analyze the tone of: {{current_story}}
Output only one word: 'positive', 'negative', or 'neutral'.""",
    output_key="tone_check_result",
)

# --- Create the agent instance ---
root_agent = StoryFlowAgent(
    name="StoryFlowAgent",
    story_generator=story_generator,
    critic=critic,
    reviser=reviser,
    grammar_check=grammar_check,
    tone_check=tone_check,
)

logger.info("StoryFlowAgent initialized")
