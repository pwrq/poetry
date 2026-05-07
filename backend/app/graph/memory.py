"""
Working memory hooks for MC Romano (create_react_agent).

pre_model_hook:  builds a compact contest digest the MC sees before each LLM call.
post_model_hook: captures MC's spoken text and broadcasts it as an agent_message event.
"""
from __future__ import annotations
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langgraph.config import get_stream_writer
from app.agents.base import next_slot


def _extract_text(content: Any) -> str:
    """Pull plain text from LangChain message content (str or content-block list)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                # Include only text blocks; skip tool_use/tool_call blocks
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts).strip()
    return ""


def pre_model_hook(state: dict) -> dict:
    """Build working memory digest for MC Romano before each LLM call.

    Returns {"llm_input_messages": [system_msg, digest_msg, ...last_10_messages]}.
    This REPLACES the raw message history the model sees with a structured digest.
    """
    cfg = state["agent_configs"].get("organizer", {})
    user_name = state["agent_configs"].get("user", {}).get("name", "Boss")

    system_text = (
        cfg.get("personality", "You are MC Romano.")
           .replace("{user_name}", user_name)
        + f"\n\nAudience member name: @{user_name}."
    )

    # ── Build compact digest ──────────────────────────────────────────────────
    lines: list[str] = []

    # Contest status
    lines.append("## Contest Status")
    round_n = state.get("current_round", 0)
    total_r = state.get("total_rounds", 3)
    phase = state.get("phase", "idle")
    lines.append(f"Round: {round_n}/{total_r} | Phase: {phase}")
    if state.get("topic"):
        lines.append(f"Topic: {state['topic']}")
    if state.get("line_limit", 0) > 0:
        lines.append(f"Line limit: {state['line_limit']}")

    # Active roster (with IDs so MC knows what to pass to run_performance)
    configs = state.get("agent_configs", {})
    contestants = [(k, v["name"]) for k, v in configs.items() if v.get("role") == "contestant"]
    judges = [(k, v["name"]) for k, v in configs.items() if v.get("role") == "judge"]
    scorekeepers = [(k, v["name"]) for k, v in configs.items() if v.get("role") == "scorekeeper"]

    lines.append("\n## Active Roster")
    if contestants:
        lines.append("Contestants: " + ", ".join(f"{n} (id='{k}')" for k, n in contestants))
    if judges:
        lines.append("Judges: " + ", ".join(f"{n} (id='{k}')" for k, n in judges))
    if scorekeepers:
        lines.append("Scorekeeper: " + ", ".join(f"{n}" for _, n in scorekeepers))
    if not (contestants or judges or scorekeepers):
        lines.append("(No agents hired yet)")

    # Poems performed this round + who still needs to go
    poems_this_round = state.get("poems_this_round", [])
    perf_order = state.get("performance_order", [])
    if poems_this_round:
        performed = [p.contestant_name for p in poems_this_round]
        lines.append(f"\n## This Round — Performed ({len(poems_this_round)})")
        lines.append(", ".join(performed))
    performed_ids = {p.contestant_id for p in poems_this_round}
    all_contestant_ids = [k for k, v in configs.items() if v.get("role") == "contestant"]
    remaining_ids = [cid for cid in all_contestant_ids if cid not in performed_ids]
    if remaining_ids and phase == "performance":
        remaining_names = [configs[cid]["name"] for cid in remaining_ids]
        lines.append(f"Still to perform: {', '.join(remaining_names)}")

    # Cumulative scores
    all_scores = state.get("round_scores", [])
    if all_scores:
        lines.append("\n## Cumulative Scores")
        totals: dict[str, float] = {}
        names: dict[str, str] = {}
        for s in all_scores:
            totals[s.contestant_id] = totals.get(s.contestant_id, 0.0) + s.total
            names[s.contestant_id] = s.contestant_name
        for cid, tot in sorted(totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {names[cid]}: {tot} pts")

    # Remaining preset topics
    preset = state.get("preset_topics", [])
    used = len(state.get("topics_used", []))
    if preset and used < total_r:
        remaining_topics = preset[used:]
        lines.append(
            "\n## Preset topics remaining: "
            + ", ".join(t or "(invent)" for t in remaining_topics)
        )
    elif not preset and phase not in ("idle", "setup", "post_contest"):
        lines.append("\n## Topics: LIVE — invent a creative topic for each round yourself.")

    # Explicit next-action hint so Romano never guesses
    lines.append("\n## NEXT ACTION")
    if phase in ("idle", ""):
        lines.append(f"→ welcome @{user_name}, call ask_audience ONCE (all setup in one question), then setup_contest")
    elif phase == "setup":
        n_c = len([k for k, v in configs.items() if v.get("role") == "contestant"])
        n_j = len([k for k, v in configs.items() if v.get("role") == "judge"])
        n_s = len([k for k, v in configs.items() if v.get("role") == "scorekeeper"])
        missing = []
        if n_c < 4:
            missing.append(f"{4 - n_c} more contestant(s)")
        if n_j < 3:
            missing.append(f"{3 - n_j} more judge(s)")
        if n_s < 1:
            missing.append("1 scorekeeper")
        if missing:
            lines.append(f"→ hire: {', '.join(missing)}")
        else:
            lines.append("→ all agents hired — announce roster to @All, then call start_round(1, topic)")
    elif phase == "performance":
        if remaining_ids:
            rem = [f"{configs[cid]['name']} (id='{cid}')" for cid in remaining_ids]
            lines.append(f"→ call run_performance for: {', '.join(rem)}")
        else:
            lines.append("→ all poems performed — call start_deliberation")
    elif phase == "deliberation":
        lines.append("→ call tally_scores — do NOT call start_deliberation again or crown_winner yet")
    elif phase == "scoring":
        next_r = round_n + 1
        if next_r <= total_r:
            lines.append(f"→ announce Round {round_n} results to @All, then call start_round({next_r}, topic)")
        else:
            lines.append(f"→ announce final Round {round_n} results to @All, then call crown_winner")
    elif phase == "post_contest":
        lines.append("→ contest complete")

    digest = "\n".join(lines)

    # Pass the last complete AIMessage+ToolMessages exchange so MC knows what
    # it last did. We MUST include complete pairs to avoid tool_use/tool_result
    # mismatch errors. Strategy: walk backwards to find the last AIMessage that
    # has tool_calls, include it plus all immediately following ToolMessages.
    all_msgs = list(state.get("messages", []))
    last_exchange: list[BaseMessage] = []
    if all_msgs:
        # Find the last AIMessage with tool_calls
        for i in range(len(all_msgs) - 1, -1, -1):
            m = all_msgs[i]
            if m.__class__.__name__ == "AIMessage" and getattr(m, "tool_calls", None):
                # Include this AIMessage + all ToolMessages that immediately follow it
                exchange = [m]
                for j in range(i + 1, len(all_msgs)):
                    if all_msgs[j].__class__.__name__ == "ToolMessage":
                        exchange.append(all_msgs[j])
                    else:
                        break
                last_exchange = exchange
                break

    return {
        "llm_input_messages": [
            SystemMessage(content=system_text),
            HumanMessage(content=digest),
        ] + last_exchange,
    }


def post_model_hook(state: dict) -> dict | None:
    """After each LLM call, broadcast MC's spoken text as an agent_message event.

    Only broadcasts if the latest AI message has non-empty text content.
    Increments next_slot so tool outputs come after MC's announcement.

    Fallback: if the AI response had no text but called ask_audience, use the
    question as Romano's spoken content so it appears in the feed.
    """
    messages = state.get("messages", [])
    if not messages:
        return None

    last = messages[-1]
    # Only process AIMessage (not HumanMessage or ToolMessage)
    if last.__class__.__name__ != "AIMessage":
        return None

    content = _extract_text(last.content)

    # Fallback: if no spoken text, check tool_calls for ask_audience question
    ask_audience_active = False
    if not content:
        tool_calls = getattr(last, "tool_calls", []) or []
        for tc in tool_calls:
            if tc.get("name") == "ask_audience":
                q = tc.get("args", {}).get("question", "")
                if q:
                    content = q
                    ask_audience_active = True
                    break
        # Also check Anthropic-style content block list for tool_use blocks
        if not content and isinstance(last.content, list):
            for block in last.content:
                if (isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("name") == "ask_audience"):
                    q = block.get("input", {}).get("question", "")
                    if q:
                        content = q
                        ask_audience_active = True
                        break

    if not content:
        return None

    write = get_stream_writer()
    slot = next_slot()
    cfg = state["agent_configs"].get("organizer", {})
    user_name = state["agent_configs"].get("user", {}).get("name", "Boss")

    # ask_audience is a private question to the user — ensure it's addressed to them
    if ask_audience_active:
        import re
        # Strip any @All prefix, then re-address to the user
        body = re.sub(r'^@All[\s\-—,;:.!?]*', '', content).strip()
        if not content.startswith(f"@{user_name}"):
            content = f"@{user_name} — {body}" if body else f"@{user_name}"

    msg_data = {
        "slot": slot,
        "agent_id": "organizer",
        "agent_name": cfg.get("name", "MC Romano"),
        "agent_role": "organizer",
        "content": content,
        "visibility": "all",
        "round_number": state.get("current_round", 0),
        "phase": state.get("phase", "idle"),
    }
    write({"type": "agent_message", "data": msg_data})

    return None
