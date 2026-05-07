"""
MC Romano's orchestration tools.

All tools are callable by create_react_agent. Tools that update graph state
return Command(update={...}); the state reducer applies the updates.

IMPORTANT: Every Command-returning tool must include a ToolMessage in
Command.update["messages"] so LangGraph's message history stays consistent.
We get the tool_call_id from `runtime: ToolRuntime` (injected by LangGraph).
Tools that only need state use InjectedState; tools that need tool_call_id use ToolRuntime.
"""
from __future__ import annotations
import re
from typing import Annotated, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import interrupt, Command
from langgraph.config import get_stream_writer

from app.agents.base import create_llm, next_slot as _next_slot
from app.models import AgentMessage, Poem, RoundScore


def _slug(name: str, prefix: str) -> str:
    """Create a safe, deterministic agent ID from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:20]
    return f"{prefix}{slug}"


def _extract_text(content: Any) -> str:
    """Pull plain text from a LangChain message content (str or list)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts).strip()
    return ""


# ── ask_audience ──────────────────────────────────────────────────────────────

@tool
def ask_audience(
    question: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Ask the audience (user) a question and pause until they type a response.
    Returns the user's answer as a plain string.
    ONLY for initial setup before calling setup_contest. Never call after that."""
    phase = state.get("phase", "idle")
    if phase not in ("idle", ""):
        return (
            f"Error: Cannot ask audience during an active contest (phase='{phase}'). "
            "Proceed autonomously — call the next appropriate tool: "
            "tally_scores (if deliberation just finished), "
            "start_round (to begin the next round), or "
            "crown_winner (after all rounds are done)."
        )
    write = get_stream_writer()
    write({"type": "state_update", "data": {
        "waiting_for_user": True,
        "waiting_prompt": question,
    }})
    response = interrupt({"prompt": question})
    write({"type": "state_update", "data": {
        "waiting_for_user": False,
        "waiting_prompt": "",
    }})
    if isinstance(response, dict):
        return response.get("message", str(response))
    return str(response)


# ── setup_contest ─────────────────────────────────────────────────────────────

@tool
def setup_contest(
    total_rounds: int,
    preset_topics: list[str],
    line_limit: int,
    runtime: ToolRuntime,
) -> Command:
    """Save the contest configuration after getting it from ask_audience.
    total_rounds: number of rounds (1-10).
    preset_topics: list of topic strings, one per round; use '' for rounds where topic will be asked live.
    line_limit: maximum poem lines (0 = no limit).
    Returns confirmation."""
    write = runtime.stream_writer
    total_rounds = max(1, min(10, total_rounds))
    topics = list(preset_topics)[:total_rounds] + [""] * max(0, total_rounds - len(preset_topics))
    write({"type": "state_update", "data": {
        "total_rounds": total_rounds,
        "line_limit": line_limit,
    }})
    summary = f"{total_rounds} rounds, topics: {topics}, line_limit: {line_limit}"
    return Command(update={
        "messages": [ToolMessage(summary, tool_call_id=runtime.tool_call_id)],
        "total_rounds": total_rounds,
        "preset_topics": topics,
        "line_limit": line_limit,
        "phase": "setup",
    })


# ── hire_contestant ───────────────────────────────────────────────────────────

# Free models cycled per role — MC Romano uses a paid model, everyone else is free.
# Only confirmed-working OpenRouter free model IDs listed here.
_CONTESTANT_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]
_JUDGE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]
_SCOREKEEPER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


@tool
def hire_contestant(
    name: str,
    personality: str,
    runtime: ToolRuntime,
) -> Command:
    """Hire a contestant poet. Registers them and makes them available for run_performance.
    name: The poet's display name (e.g. 'Shakespeare').
    personality: System prompt describing their writing style and character.
    Returns the contestant_id to use in run_performance."""
    write = runtime.stream_writer
    contestant_id = _slug(name, "contestant_")
    cfg = {
        "id": contestant_id,
        "name": name,
        "role": "contestant",
        "model": _CONTESTANT_MODELS[abs(hash(name)) % len(_CONTESTANT_MODELS)],
        "personality": personality,
    }
    write({"type": "config_sync", "data": cfg})
    return Command(update={
        "messages": [ToolMessage(f"Contestant '{name}' hired (id='{contestant_id}')", tool_call_id=runtime.tool_call_id)],
        "agent_configs": {contestant_id: cfg},
        "agent_memories": {contestant_id: []},
    })


# ── hire_judge ────────────────────────────────────────────────────────────────

@tool
def hire_judge(
    name: str,
    personality: str,
    runtime: ToolRuntime,
) -> Command:
    """Hire a poetry judge. They will deliberate and score poems each round.
    name: The judge's display name (e.g. 'Prof. Stern').
    personality: System prompt describing their judging style.
    Returns the judge_id."""
    write = runtime.stream_writer
    judge_id = _slug(name, "judge_")
    cfg = {
        "id": judge_id,
        "name": name,
        "role": "judge",
        "model": _JUDGE_MODELS[abs(hash(name)) % len(_JUDGE_MODELS)],
        "personality": personality,
    }
    write({"type": "config_sync", "data": cfg})
    return Command(update={
        "messages": [ToolMessage(f"Judge '{name}' hired (id='{judge_id}')", tool_call_id=runtime.tool_call_id)],
        "agent_configs": {judge_id: cfg},
        "agent_memories": {judge_id: []},
    })


# ── hire_scorekeeper ──────────────────────────────────────────────────────────

@tool
def hire_scorekeeper(
    name: str,
    personality: str,
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime,
) -> Command:
    """Hire the contest scorekeeper. They tally scores and announce final results.
    Only one scorekeeper is needed. Always uses id='scorekeeper'.
    name: Display name (e.g. 'The Abacus').
    personality: System prompt."""
    write = runtime.stream_writer
    cfg = {
        "id": "scorekeeper",
        "name": name,
        "role": "scorekeeper",
        "model": _SCOREKEEPER_MODEL,
        "personality": personality,
    }
    write({"type": "config_sync", "data": cfg})
    return Command(update={
        "messages": [ToolMessage(f"Scorekeeper '{name}' hired", tool_call_id=runtime.tool_call_id)],
        "agent_configs": {"scorekeeper": cfg},
        "agent_memories": {"scorekeeper": []},
    })


# ── start_round ───────────────────────────────────────────────────────────────

@tool
def start_round(
    round_number: int,
    topic: str,
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime,
) -> Command:
    """Begin a new contest round. Resets per-round state and sets the topic.
    round_number: Which round this is (1-based).
    topic: The poem topic/theme for this round.
    Returns confirmation. Call run_performance next for each contestant."""
    write = runtime.stream_writer
    write({"type": "state_update", "data": {
        "current_round": round_number,
        "phase": "performance",
        "topic": topic,
        "waiting_for_user": False,
        "waiting_prompt": "",
    }})
    topics_used = list(state.get("topics_used", [])) + [topic]
    return Command(update={
        "messages": [ToolMessage(f"Round {round_number} started. Topic: '{topic}'.", tool_call_id=runtime.tool_call_id)],
        "current_round": round_number,
        "phase": "performance",
        "topic": topic,
        "poems_this_round": [],
        "scores_this_round": [],
        "deliberation_round": 0,
        "performance_order": [],
        "topics_used": topics_used,
    })


# ── run_performance ───────────────────────────────────────────────────────────

@tool
def run_performance(
    contestant_id: str,
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime,
) -> Command:
    """Have a contestant perform their poem for the current round.
    contestant_id: The id returned when you hired this contestant (e.g. 'contestant_shakespeare').
    Call this once per contestant, in the performance order you choose.
    Returns the poem text."""
    write = runtime.stream_writer
    cfg = state["agent_configs"].get(contestant_id)
    if not cfg:
        return Command(update={
            "messages": [ToolMessage(f"Error: contestant '{contestant_id}' not found.", tool_call_id=runtime.tool_call_id)],
        })

    topic = state.get("topic", "freestyle")
    round_num = state.get("current_round", 1)
    total = state.get("total_rounds", 3)
    line_limit = state.get("line_limit", 0)
    memory = list(state["agent_memories"].get(contestant_id, []))

    limit_rule = (
        f" IMPORTANT: Your poem must be at most {line_limit} lines — exceeding this is a rule violation."
        if line_limit > 0 else ""
    )
    prompt = (
        f"The topic is: '{topic}'. Round {round_num} of {total}.{limit_rule} "
        f"Write your poem now. Stay in character. "
        f"IMPORTANT: start your response with exactly '@All —' on the first line, "
        f"then the poem. Output nothing else."
    )
    messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
    llm = create_llm(cfg.get("model"))
    try:
        response = llm.invoke(messages)
        content = response.content if isinstance(response.content, str) else _extract_text(response.content)
    except Exception:
        try:
            response = create_llm(None).invoke(messages)
            content = response.content if isinstance(response.content, str) else _extract_text(response.content)
        except Exception:
            content = f"@All —\n{cfg['name']} stands silent at the podium. (model unavailable)"

    slot = _next_slot()
    poem = Poem(
        contestant_id=contestant_id,
        contestant_name=cfg["name"],
        text=content,
        round_number=round_num,
    )
    msg = AgentMessage(
        slot=slot,
        agent_id=contestant_id,
        agent_name=cfg["name"],
        agent_role="contestant",
        content=content,
        visibility="all",
        round_number=round_num,
        phase="performance",
    )
    write({"type": "agent_message", "data": msg.model_dump()})

    new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=content)]
    perf_order = list(state.get("performance_order", [])) + [contestant_id]
    return Command(update={
        "messages": [ToolMessage(f"{cfg['name']} performed their poem.", tool_call_id=runtime.tool_call_id)],
        "poems": [poem],
        "poems_this_round": state.get("poems_this_round", []) + [poem],
        "performance_order": perf_order,
        "agent_memories": {contestant_id: new_memory},
    })


# ── start_deliberation ────────────────────────────────────────────────────────

@tool
async def start_deliberation(
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime,
) -> Command:
    """Run the full judge deliberation for the current round.
    Judges discuss and score all poems performed this round.
    Returns score summary. Call tally_scores next."""
    from app.graph.deliberation import judge_deliberation
    result = await judge_deliberation(state)
    scores = result.get("scores_this_round", [])
    summary = ", ".join(
        f"{s.contestant_name}: {int(s.total)}" for s in scores
    ) if scores else "no scores"
    return Command(update={
        "messages": [ToolMessage(f"Deliberation done. Scores: {summary}", tool_call_id=runtime.tool_call_id)],
        "scores_this_round": scores,
        "deliberation_messages": result.get("deliberation_messages", []),
        "agent_memories": result.get("agent_memories", {}),
        "phase": "deliberation",
    })


# ── tally_scores ──────────────────────────────────────────────────────────────

@tool
def tally_scores(
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime,
) -> Command:
    """Have the scorekeeper tally round scores and send results to MC.
    Call this after start_deliberation. Returns tally message.
    After this returns, announce the round results yourself to @All."""
    write = runtime.stream_writer
    cfg = state["agent_configs"].get("scorekeeper")
    if not cfg:
        return Command(update={
            "messages": [ToolMessage("Error: no scorekeeper hired.", tool_call_id=runtime.tool_call_id)],
        })

    scores = state.get("scores_this_round", [])
    round_num = state.get("current_round", 1)
    all_scores = list(state.get("round_scores", [])) + list(scores)

    from app.agents.scorekeeper import _cumulative
    cumulative = _cumulative(all_scores)

    import re as _re
    org_name = state["agent_configs"].get("organizer", {}).get("name", "MC Romano")
    org_mention = max(_re.findall(r"\w+", org_name), key=len)

    scores_text = "\n".join(
        f"  {s.contestant_name}: on-topic={s.on_topic}, originality={s.originality}, "
        f"artistic={s.artistic_value}, total={int(s.total)}"
        for s in scores
    )
    standings_text = "\n".join(
        f"  {c.rank}. {c.contestant_name}: {c.total} pts" for c in cumulative
    )
    prompt = (
        f"Start with '@{org_mention} —'. You have tallied Round {round_num} scores:\n{scores_text}\n\n"
        f"Cumulative standings:\n{standings_text}\n\n"
        f"Hand these results to @{org_mention} — brief, in-character, 1-2 sentences. "
        f"Do NOT announce to @All — that is the MC's job. Begin with '@{org_mention} —'."
    )

    memory = list(state["agent_memories"].get("scorekeeper", []))
    llm = create_llm(cfg.get("model"))
    messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
    try:
        response = llm.invoke(messages)
        content = response.content if isinstance(response.content, str) else _extract_text(response.content)
    except Exception:
        try:
            content = _extract_text(create_llm(None).invoke(messages).content)
        except Exception:
            content = f"@{org_mention} — Round {round_num} tallied. (scorekeeper unavailable)"

    msg = AgentMessage(
        slot=_next_slot(),
        agent_id="scorekeeper",
        agent_name=cfg["name"],
        agent_role="scorekeeper",
        content=content,
        visibility="all",
        round_number=round_num,
        phase="scoring",
    )
    write({"type": "agent_message", "data": msg.model_dump()})
    write({
        "type": "scores",
        "data": {
            "round_number": round_num,
            "scores": [s.model_dump() for s in scores],
            "cumulative": [c.model_dump() for c in cumulative],
        },
    })

    new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=content)]
    return Command(update={
        "messages": [ToolMessage(content, tool_call_id=runtime.tool_call_id)],
        "round_scores": scores,
        "agent_memories": {"scorekeeper": new_memory},
        "phase": "scoring",
    })


# ── crown_winner ──────────────────────────────────────────────────────────────

@tool
def crown_winner(
    state: Annotated[dict, InjectedState],
    runtime: ToolRuntime,
) -> Command:
    """Have the scorekeeper deliver the final dramatic announcement.
    Call this after the last round's tally_scores. Ends the contest."""
    write = runtime.stream_writer
    cfg = state["agent_configs"].get("scorekeeper")
    if not cfg:
        return Command(update={
            "messages": [ToolMessage("Error: no scorekeeper hired.", tool_call_id=runtime.tool_call_id)],
            "phase": "post_contest",
        })

    all_scores = list(state.get("round_scores", []))
    from app.agents.scorekeeper import _cumulative
    cumulative = _cumulative(all_scores)
    winner = cumulative[0] if cumulative else None

    standings_text = "\n".join(
        f"  {c.rank}. {c.contestant_name}: {c.total} pts" for c in cumulative
    )
    prompt = (
        f"Start with '@All —'. The contest is over! Final standings:\n{standings_text}\n\n"
        f"The winner is {winner.contestant_name if winner else 'unknown'} "
        f"with {winner.total if winner else 0} points! "
        "Deliver the ultimate dramatic announcement. Crown the champion! Begin with '@All —'."
    )

    memory = list(state["agent_memories"].get("scorekeeper", []))
    llm = create_llm(cfg.get("model"))
    messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
    try:
        response = llm.invoke(messages)
        content = response.content if isinstance(response.content, str) else _extract_text(response.content)
    except Exception:
        try:
            content = _extract_text(create_llm(None).invoke(messages).content)
        except Exception:
            winner_name = winner.contestant_name if winner else "unknown"
            content = f"@All — The winner is {winner_name}! (scorekeeper unavailable)"

    msg = AgentMessage(
        slot=_next_slot(),
        agent_id="scorekeeper",
        agent_name=cfg["name"],
        agent_role="scorekeeper",
        content=content,
        visibility="all",
        round_number=state.get("current_round", 0),
        phase="post_contest",
    )
    write({"type": "agent_message", "data": msg.model_dump()})

    final_results = {
        "winner": {
            "contestant_id": winner.contestant_id,
            "contestant_name": winner.contestant_name,
            "total": winner.total,
        } if winner else {},
        "standings": [c.model_dump() for c in cumulative],
    }
    write({"type": "final_results", "data": final_results})

    new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=content)]
    return Command(update={
        "messages": [ToolMessage(content, tool_call_id=runtime.tool_call_id)],
        "agent_memories": {"scorekeeper": new_memory},
        "phase": "post_contest",
    })


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = [
    ask_audience,
    setup_contest,
    hire_contestant,
    hire_judge,
    hire_scorekeeper,
    start_round,
    run_performance,
    start_deliberation,
    tally_scores,
    crown_winner,
]
