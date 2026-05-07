from __future__ import annotations
from langgraph.prebuilt import create_react_agent

from app.agents.base import create_llm, RUNTIME_DEFAULTS
from app.agents.tools import TOOLS
from app.graph.memory import pre_model_hook, post_model_hook
from app.graph.state import OrchestratorState


def build_contest_graph(checkpointer=None, model: str | None = None):
    """Build and compile the MC Romano orchestrator graph.

    MC Romano is a ReAct agent that runs the entire contest via tool calls.
    The graph has no hardcoded edges — MC decides the contest flow dynamically.
    """
    model_id = model or RUNTIME_DEFAULTS["organizer"]["model"]
    mc_model = create_llm(model_id)

    return create_react_agent(
        model=mc_model,
        tools=TOOLS,
        state_schema=OrchestratorState,
        pre_model_hook=pre_model_hook,
        post_model_hook=post_model_hook,
        checkpointer=checkpointer,
    )
