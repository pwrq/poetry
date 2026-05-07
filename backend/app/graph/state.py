from __future__ import annotations
from typing import Annotated, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps

from app.models import Poem, RoundScore


def _add(a: list, b: list) -> list:
    return a + b


def _merge(a: dict, b: dict) -> dict:
    """Merge-reducer: new values win on key conflict. Enables parallel hiring tools."""
    return {**a, **b}


class OrchestratorState(TypedDict):
    # ── ReAct agent required ────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]
    remaining_steps: RemainingSteps  # managed by create_react_agent; NOT set in initial state

    # ── Core contest data ───────────────────────────────────────────────
    current_round: int
    total_rounds: int
    phase: str
    topic: str
    contest_number: int

    # Performance order (MC decides)
    performance_order: list[str]  # list of contestant IDs in order

    # ── Append-only accumulated data ────────────────────────────────────
    poems: Annotated[list[Poem], _add]
    round_scores: Annotated[list[RoundScore], _add]

    # ── Per-round working data (reset by start_round tool) ──────────────
    poems_this_round: list[Poem]

    # ── Deliberation sub-state ──────────────────────────────────────────
    deliberation_messages: Annotated[list[dict], _add]
    deliberation_round: int
    scores_this_round: list[RoundScore]

    # ── Global slot counter ─────────────────────────────────────────────
    next_slot: int

    # ── Agent config & memory (merge reducers for parallel hiring) ───────
    agent_configs: Annotated[dict[str, dict], _merge]
    agent_memories: Annotated[dict[str, list[Any]], _merge]

    # ── Judging mode ────────────────────────────────────────────────────
    judging_mode: str  # "sequential" | "autogen"

    # ── User interaction ────────────────────────────────────────────────
    waiting_for_user: bool
    waiting_prompt: str

    # ── Setup data ──────────────────────────────────────────────────────
    preset_topics: list[str]   # per-round topics; "" = not specified for that round
    topics_used: list[str]     # topics confirmed so far
    line_limit: int            # max lines per poem (0 = no limit)


def make_initial_state(agent_configs: dict[str, dict]) -> dict:
    """Return initial graph state. Does NOT set remaining_steps (managed by create_react_agent)."""
    user_name = agent_configs.get("user", {}).get("name", "Boss")
    return {
        "messages": [HumanMessage(
            content=(
                f"Showtime! Welcome @{user_name}, then call ask_audience ONCE with a SINGLE question "
                f"that asks for: (1) number of rounds (1-10), (2) topics per round or 'live', "
                f"(3) line limit or 'none'. Parse the reply yourself and call setup_contest immediately."
            )
        )],
        "current_round": 0,
        "total_rounds": 3,
        "phase": "idle",
        "topic": "",
        "contest_number": 1,
        "performance_order": [],
        "poems": [],
        "round_scores": [],
        "poems_this_round": [],
        "deliberation_messages": [],
        "deliberation_round": 0,
        "scores_this_round": [],
        "judging_mode": "sequential",
        "next_slot": 1,
        "agent_configs": agent_configs,
        "agent_memories": {aid: [] for aid in agent_configs},
        "waiting_for_user": False,
        "waiting_prompt": "",
        "preset_topics": [],
        "topics_used": [],
        "line_limit": 0,
    }
