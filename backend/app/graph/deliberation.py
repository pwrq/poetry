from __future__ import annotations
import asyncio
import re as _re
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.config import get_stream_writer

from app.agents.base import create_llm, next_slot as _next_slot
from app.agents.judge import _parse_scores, check_consensus
from app.models import AgentMessage, RoundScore, Poem

MAX_DELIBERATION_ROUNDS = 2


def _poem_body(text: str) -> str:
    """Return poem text with any leading @Address line stripped."""
    stripped = text.strip()
    first_nl = stripped.find("\n")
    if first_nl > 0:
        first_line = stripped[:first_nl].strip()
        if _re.match(r'^@\w+', first_line):
            return stripped[first_nl + 1:].strip()
    return stripped


def _line_count(text: str) -> int:
    """Count non-empty lines in the poem body (excluding @Address prefix)."""
    return len([ln for ln in _poem_body(text).split("\n") if ln.strip()])


# ── Shared schema ─────────────────────────────────────────────────────────────

SCORE_SCHEMA_ALL = """
Respond in two parts:
1. Start your response with '@Judges —' then a short comment (1-3 sentences).
2. Your proposed scores as JSON — one object per contestant on its own line at the end:
{"contestant_id": "...", "on_topic": X, "originality": X, "artistic_value": X}
(X is 1-10. No trailing commas. Use the contestant's display name as contestant_id.)
"""


# ── Single-poem consensus helper ──────────────────────────────────────────────

def _check_consensus_single(poem: Poem, all_proposed: list[list[dict]]) -> tuple[bool, list[RoundScore]]:
    """Consensus check for a single poem across all judges."""
    if not all_proposed:
        return True, []
    scores_for = []
    for proposed in all_proposed:
        for s in proposed:
            if s.get("contestant_id") == poem.contestant_id:
                scores_for.append(s)
                break
    if not scores_for:
        return True, [RoundScore(
            contestant_id=poem.contestant_id, contestant_name=poem.contestant_name,
            on_topic=5.0, originality=5.0, artistic_value=5.0, total=15.0,
        )]
    on_topics = [s.get("on_topic", 5.0) for s in scores_for]
    originals = [s.get("originality", 5.0) for s in scores_for]
    arts = [s.get("artistic_value", 5.0) for s in scores_for]
    agreed = (max(on_topics) - min(on_topics) <= 1.5 and
              max(originals) - min(originals) <= 1.5 and
              max(arts) - min(arts) <= 1.5)
    on_i = round(sum(on_topics) / len(on_topics))
    orig_i = round(sum(originals) / len(originals))
    art_i = round(sum(arts) / len(arts))
    result = [RoundScore(
        contestant_id=poem.contestant_id, contestant_name=poem.contestant_name,
        on_topic=float(on_i), originality=float(orig_i), artistic_value=float(art_i),
        total=float(on_i + orig_i + art_i),
    )]
    return agreed, result


# ── Lead-judge submission message ────────────────────────────────────────────

def _mention(display_name: str) -> str:
    """Return the longest single word from a display name for use as @mention."""
    words = _re.findall(r'\w+', display_name)
    return max(words, key=len) if words else display_name


async def _lead_judge_submit(
    state: dict,
    lead_judge_id: str,
    scores: list[RoundScore],
    all_memories: dict,
    write,
) -> dict:
    """Lead judge sends a visible message to @ScoreKeeper with final scores."""
    cfg = state["agent_configs"][lead_judge_id]
    llm = create_llm(cfg.get("model"))
    memory = list(all_memories.get(lead_judge_id, []))

    sk_cfg = next(
        (v for v in state["agent_configs"].values() if v.get("role") == "scorekeeper"),
        None,
    )
    sk_name = sk_cfg["name"] if sk_cfg else "ScoreKeeper"
    sk_mention = _mention(sk_name)

    score_cards = ", ".join(
        f"{s.contestant_name}: on_topic={s.on_topic} originality={s.originality} artistic={s.artistic_value}"
        for s in scores
    )
    prompt = (
        f"Start your response with '@{sk_mention} —'. "
        f"The panel has scored Round {state.get('current_round', 1)}. "
        f"Hand over the score cards: {score_cards}. "
        f"1-2 sentences in character — do NOT compute totals, that is @{sk_mention}'s job. "
        f"Start with '@{sk_mention} —'."
    )
    messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
    try:
        response = await llm.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
    except Exception:
        content = f"@{sk_mention} — The panel has reached a verdict. Here are the score cards: {score_cards}."
    new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=content)]
    all_memories[lead_judge_id] = new_memory

    msg = AgentMessage(
        slot=_next_slot(), agent_id=lead_judge_id, agent_name=cfg["name"],
        agent_role="judge", content=content,
        visibility="all",
        round_number=state.get("current_round", 1), phase="deliberation",
    )
    write({"type": "agent_message", "data": msg.model_dump()})
    return all_memories


# ── Sequential mode ───────────────────────────────────────────────────────────

async def _run_sequential(state: dict) -> dict:
    """Judges evaluate ALL poems_this_round together. Rotating lead judge."""
    write = get_stream_writer()
    round_num = state.get("current_round", 1)
    poems = state.get("poems_this_round", [])

    # Discover judges dynamically from state
    judge_ids = [k for k, v in state["agent_configs"].items() if v.get("role") == "judge"]
    if not judge_ids:
        return {
            "scores_this_round": [],
            "deliberation_messages": [],
            "agent_memories": state.get("agent_memories", {}),
            "phase": "deliberation",
        }

    lead_idx = (round_num - 1) % len(judge_ids)
    ordered = judge_ids[lead_idx:] + judge_ids[:lead_idx]
    lead_judge_id = ordered[0]

    delib_history: list[dict] = []
    all_memories = dict(state.get("agent_memories", {}))
    messages_out: list[AgentMessage] = []
    per_judge_scores: dict[str, list[dict]] = {}

    line_limit = state.get("line_limit", 0)

    def _poem_header(p: Poem) -> str:
        lc = _line_count(p.text)
        if line_limit > 0:
            over = " ⚠ OVER LIMIT" if lc > line_limit else ""
            return f"--- {p.contestant_name} ({lc} lines, limit {line_limit}){over} ---"
        return f"--- {p.contestant_name} ({lc} lines) ---"

    poems_text = "\n\n".join(
        f"{_poem_header(p)}\n{_poem_body(p.text)}" for p in poems
    )
    limit_note = (
        f"\nContest rule: poems must not exceed {line_limit} lines. "
        f"The line counts above are exact — trust them, do not recount.\n"
        if line_limit > 0 else ""
    )

    for _delib_round in range(MAX_DELIBERATION_ROUNDS):
        for judge_id in ordered:
            cfg = state["agent_configs"][judge_id]
            llm = create_llm(cfg.get("model"))
            memory = list(all_memories.get(judge_id, []))

            prior = ""
            if delib_history:
                prior = "\n\nPrior discussion:\n" + "\n".join(
                    f"{d['judge_name']}: {d['text']}" for d in delib_history
                )

            prompt = (
                f"@Judges — Round {round_num} poems to score:\n\n{poems_text}"
                f"{prior}\n\nTopic: {state.get('topic', '')}\n"
                + limit_note
                + "\nScore each poem on: on_topic (1-10), originality (1-10), artistic_value (1-10).\n"
                + SCORE_SCHEMA_ALL
            )

            messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
            try:
                response = await llm.ainvoke(messages)
                content = response.content if isinstance(response.content, str) else str(response.content)
                discussion_text, proposed_scores = _parse_scores(content, poems)
            except Exception:
                try:
                    response = await create_llm(None).ainvoke(messages)
                    content = response.content if isinstance(response.content, str) else str(response.content)
                    discussion_text, proposed_scores = _parse_scores(content, poems)
                except Exception:
                    discussion_text = "@Judges — (abstained due to model error)"
                    proposed_scores = []

            display = discussion_text or "(no comment)"

            msg = AgentMessage(
                slot=_next_slot(), agent_id=judge_id, agent_name=cfg["name"],
                agent_role="judge", content=display,
                visibility="judges_only", round_number=round_num, phase="deliberation",
            )
            write({"type": "agent_message", "data": msg.model_dump()})
            messages_out.append(msg)

            new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=display)]
            all_memories[judge_id] = new_memory
            delib_history.append({
                "judge_id": judge_id, "judge_name": cfg["name"],
                "text": discussion_text or "",
            })
            if proposed_scores:
                per_judge_scores[judge_id] = proposed_scores

        all_proposed = list(per_judge_scores.values())
        agreed, final_scores = check_consensus(state, all_proposed)
        if agreed:
            break

    _, final_scores = check_consensus(state, list(per_judge_scores.values()))
    all_memories = await _lead_judge_submit(state, lead_judge_id, final_scores, all_memories, write)

    return {
        "messages": messages_out,
        "deliberation_messages": delib_history,
        "agent_memories": all_memories,
        "scores_this_round": final_scores,
        "phase": "deliberation",
    }


# ── AutoGen mode ──────────────────────────────────────────────────────────────

async def _run_autogen(state: dict) -> dict:
    """All judges score ALL poems concurrently. Consensus check + optional discussion."""
    write = get_stream_writer()
    round_num = state.get("current_round", 1)
    poems = state.get("poems_this_round", [])

    # Discover judges dynamically
    judge_ids = [k for k, v in state["agent_configs"].items() if v.get("role") == "judge"]
    if not judge_ids:
        return {
            "scores_this_round": [],
            "deliberation_messages": [],
            "agent_memories": state.get("agent_memories", {}),
            "phase": "deliberation",
        }

    lead_idx = (round_num - 1) % len(judge_ids)
    ordered = judge_ids[lead_idx:] + judge_ids[:lead_idx]
    lead_judge_id = ordered[0]

    all_memories = dict(state.get("agent_memories", {}))
    messages_out: list[AgentMessage] = []

    line_limit = state.get("line_limit", 0)

    def _poem_header(p: Poem) -> str:
        lc = _line_count(p.text)
        if line_limit > 0:
            over = " ⚠ OVER LIMIT" if lc > line_limit else ""
            return f"--- {p.contestant_name} ({lc} lines, limit {line_limit}){over} ---"
        return f"--- {p.contestant_name} ({lc} lines) ---"

    poems_text = "\n\n".join(
        f"{_poem_header(p)}\n{_poem_body(p.text)}" for p in poems
    )
    limit_note = (
        f"\nContest rule: poems must not exceed {line_limit} lines. "
        f"The line counts above are exact — trust them, do not recount.\n"
        if line_limit > 0 else ""
    )

    # ── Phase 1: CONCURRENT independent scoring ───────────────────────
    async def _score_independently(judge_id: str):
        cfg = state["agent_configs"][judge_id]
        llm = create_llm(cfg.get("model"))
        memory = list(all_memories.get(judge_id, []))
        prompt = (
            f"@Judges — Score ALL poems INDEPENDENTLY (do not share scores yet).\n\n"
            f"{poems_text}\n\nTopic: {state.get('topic', '')}\n"
            + limit_note
            + "\nScore each poem on: on_topic (1-10), originality (1-10), artistic_value (1-10).\n"
            + SCORE_SCHEMA_ALL
        )
        messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
        try:
            response = await llm.ainvoke(messages)
            content = response.content if isinstance(response.content, str) else str(response.content)
            discussion_text, proposed = _parse_scores(content, poems)
        except Exception:
            try:
                response = await create_llm(None).ainvoke(messages)
                content = response.content if isinstance(response.content, str) else str(response.content)
                discussion_text, proposed = _parse_scores(content, poems)
            except Exception:
                discussion_text = "@Judges — (abstained due to model error)"
                proposed = []

        display = discussion_text or "(no comment)"
        new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=display)]
        return judge_id, discussion_text, proposed, display, new_memory

    tasks = [asyncio.create_task(_score_independently(jid)) for jid in ordered]

    per_judge_scores: dict[str, list[dict]] = {}
    independent_comments: dict[str, str] = {}
    for coro in asyncio.as_completed(tasks):
        judge_id, discussion_text, proposed, display, new_memory = await coro
        msg = AgentMessage(
            slot=_next_slot(), agent_id=judge_id,
            agent_name=state["agent_configs"][judge_id]["name"],
            agent_role="judge", content=display,
            visibility="judges_only", round_number=round_num, phase="deliberation",
        )
        write({"type": "agent_message", "data": msg.model_dump()})
        messages_out.append(msg)
        if proposed:
            per_judge_scores[judge_id] = proposed
        independent_comments[judge_id] = discussion_text or ""
        all_memories[judge_id] = new_memory

    # ── Phase 2: Sequential discussion if not in consensus ───────────
    agreed, final_scores = check_consensus(state, list(per_judge_scores.values()))
    delib_history = [
        {
            "judge_id": jid,
            "judge_name": state["agent_configs"][jid]["name"],
            "text": independent_comments[jid],
        }
        for jid in ordered
    ]

    if not agreed:
        for _delib_round in range(MAX_DELIBERATION_ROUNDS):
            prior = "\n\nInitial independent scores:\n" + "\n".join(
                f"  {state['agent_configs'][jid]['name']}: {independent_comments[jid]}"
                for jid in ordered
            )
            if len(delib_history) > len(ordered):
                prior += "\n\nDiscussion so far:\n" + "\n".join(
                    f"  {d['judge_name']}: {d['text']}"
                    for d in delib_history[len(ordered):]
                )
            for judge_id in ordered:
                cfg = state["agent_configs"][judge_id]
                llm = create_llm(cfg.get("model"))
                memory = list(all_memories.get(judge_id, []))
                prompt = (
                    f"@Judges — Deliberating on Round {round_num} poems.\n"
                    f"Topic: {state.get('topic', '')}\n\n{poems_text}"
                    + limit_note + prior
                    + "\n\nNot yet in agreement. Argue your position and provide revised scores.\n"
                    + SCORE_SCHEMA_ALL
                )
                messages = [SystemMessage(content=cfg["personality"])] + memory + [HumanMessage(content=prompt)]
                try:
                    response = await llm.ainvoke(messages)
                    content = response.content if isinstance(response.content, str) else str(response.content)
                    discussion_text, proposed = _parse_scores(content, poems)
                except Exception:
                    try:
                        response = await create_llm(None).ainvoke(messages)
                        content = response.content if isinstance(response.content, str) else str(response.content)
                        discussion_text, proposed = _parse_scores(content, poems)
                    except Exception:
                        discussion_text = "@Judges — (abstained due to model error)"
                        proposed = []
                if proposed:
                    per_judge_scores[judge_id] = proposed
                display = discussion_text or "(no comment)"
                msg = AgentMessage(
                    slot=_next_slot(), agent_id=judge_id, agent_name=cfg["name"],
                    agent_role="judge", content=display,
                    visibility="judges_only", round_number=round_num, phase="deliberation",
                )
                write({"type": "agent_message", "data": msg.model_dump()})
                messages_out.append(msg)
                new_memory = memory + [HumanMessage(content=prompt), AIMessage(content=display)]
                all_memories[judge_id] = new_memory
                delib_history.append({
                    "judge_id": judge_id, "judge_name": cfg["name"],
                    "text": discussion_text or "",
                })
            agreed, final_scores = check_consensus(state, list(per_judge_scores.values()))
            if agreed:
                break
        _, final_scores = check_consensus(state, list(per_judge_scores.values()))

    # ── Phase 3: Lead judge submits to @ScoreKeeper ───────────────────
    all_memories = await _lead_judge_submit(state, lead_judge_id, final_scores, all_memories, write)

    return {
        "messages": messages_out,
        "deliberation_messages": delib_history,
        "agent_memories": all_memories,
        "scores_this_round": final_scores,
        "phase": "deliberation",
    }


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def judge_deliberation(state: dict) -> dict:
    """Dispatcher: routes to sequential or autogen based on judging_mode."""
    if not state.get("poems_this_round"):
        return {
            "scores_this_round": [],
            "deliberation_messages": [],
            "agent_memories": state.get("agent_memories", {}),
            "phase": "deliberation",
        }
    if state.get("judging_mode", "sequential") == "autogen":
        return await _run_autogen(state)
    return await _run_sequential(state)
