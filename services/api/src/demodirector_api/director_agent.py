from collections.abc import Callable, Sequence

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset

from demodirector_api.google_ai import GoogleAISettings

DIRECTOR_INSTRUCTION = """You are DemoDirector's planning coordinator.
Use only grounded project context supplied by approved tools and return typed plans.
Never invent browser actions, product claims, or rendering commands.
Browser capture and media rendering are executed by deterministic services, not by you.
"""

DEMO_QA_INSTRUCTION = """You are DemoDirector's Demo QA Agent.
Compare typed brief requirements only with supplied storyboard, narration, capture evidence,
and timeline metadata. Cite supplied IDs, identify partial or missing coverage, and never invent
evidence. Use product language such as Brief Coverage and Demo QA, not contest judging language.
"""

type AgentTool = Callable[..., object] | BaseTool | BaseToolset


def create_director_agent(
    model_name: str,
    tools: Sequence[AgentTool] = (),
) -> Agent:
    return Agent(
        name="demodirector_director",
        model=model_name,
        description="Coordinates grounded product understanding and demo planning.",
        instruction=DIRECTOR_INSTRUCTION,
        tools=list(tools),
    )


def create_director_workflow(
    model_name: str,
    tools: Sequence[AgentTool] = (),
) -> App:
    return App(
        name="demodirector",
        root_agent=create_director_agent(model_name, tools),
    )


def create_demo_qa_agent(model_name: str) -> Agent:
    return Agent(
        name="demodirector_demo_qa",
        model=model_name,
        description="Checks a finished demo against its original brief.",
        instruction=DEMO_QA_INSTRUCTION,
    )


_settings = GoogleAISettings.from_environment()
root_agent = create_director_agent(_settings.model_name)
app = App(name="demodirector", root_agent=root_agent)
