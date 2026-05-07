"""
Organizer utilities kept for mid-contest side-channel chat.

All graph-node organizer functions (welcome, react, announce, etc.) have been
removed — those are now handled by MC Romano's ReAct loop and post_model_hook.
"""
from __future__ import annotations
import json
import re
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.base import create_llm


def parse_setup_message(organizer_cfg: dict, message: str, rounds: int) -> dict:
    """
    Use the organizer LLM to extract structured setup data from a freeform user message.
    Returns: {"topics": list[str], "line_limit": int}
    topics has exactly `rounds` entries; "" means not specified for that round.
    line_limit is 0 if not mentioned.
    """
    llm = create_llm(organizer_cfg.get("model"), temperature=0)
    prompt = (
        f'The contest host said: "{message}"\n'
        f"They want {rounds} rounds.\n\n"
        f"Extract:\n"
        f'1. topics: a JSON array of exactly {rounds} strings — the theme/topic for each round '
        f'(use "" for rounds where no topic was given).\n'
        f'2. line_limit: the maximum number of poem lines as an integer (0 if not mentioned).\n\n'
        f"Output ONLY valid JSON in this exact format:\n"
        f'{{"topics": ["...", "..."], "line_limit": 0}}\n\n'
        f"Examples:\n"
        f'- "3 rounds" → {{"topics": ["", "", ""], "line_limit": 0}}\n'
        f'- "2 rounds, first about cats, max 8 lines" → {{"topics": ["cats", ""], "line_limit": 8}}\n'
        f'- "3 rounds: love, war, nature, no limit" → {{"topics": ["love", "war", "nature"], "line_limit": 0}}\n'
        f'- "1 round about robots, 12 lines max" → {{"topics": ["robots"], "line_limit": 12}}\n'
    )
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        content = content.strip()
        # Strip markdown code fences if present
        if "```" in content:
            content = re.sub(r"```[a-z]*", "", content).replace("```", "").strip()
        # Extract JSON object even if model wraps it in explanatory text
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            content = content[start:end + 1]
        parsed = json.loads(content)
        topics = [str(t).strip() for t in parsed.get("topics", [])]
        topics = topics[:rounds] + [""] * max(0, rounds - len(topics))
        line_limit = int(parsed.get("line_limit", 0) or 0)
        return {"topics": topics, "line_limit": line_limit}
    except Exception:
        return {"topics": [""] * rounds, "line_limit": 0}


async def organizer_chat(
    user_name: str,
    user_message: str,
    agent_cfg: dict,
    recent_messages: list[dict],
    slot: int,
) -> dict:
    """
    Standalone (outside-graph) MC Romano response to a mid-contest user chat message.
    Called from main.py when the graph is running but not at an interrupt.
    """
    from datetime import datetime, timezone
    import asyncio

    llm = create_llm(agent_cfg.get("model"))
    system_text = (
        agent_cfg["personality"].replace("{user_name}", user_name)
        + f"\n\nThe audience member's name is {user_name!r}. Address them as @{user_name}."
    )

    context_lines = []
    for m in recent_messages[-10:]:
        context_lines.append(f"[{m.get('agent_name', '?')}]: {m.get('content', '')[:200]}")
    context = "\n".join(context_lines) if context_lines else "(contest just started)"

    prompt = (
        f"Current contest context (recent messages):\n{context}\n\n"
        f"@{user_name} says to you: '{user_message}'\n\n"
        f"Respond in character. Address @All, individual agents, or @{user_name} as fits. "
        f"Start with the appropriate @mention."
    )

    messages = [SystemMessage(content=system_text), HumanMessage(content=prompt)]
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, llm.invoke, messages)
    content = response.content
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    return {
        "type": "agent_message",
        "data": {
            "slot": slot,
            "agent_id": "organizer",
            "agent_name": agent_cfg["name"],
            "agent_role": "organizer",
            "content": content,
            "visibility": "all",
            "round_number": 0,
            "phase": "chat",
            "timestamp": ts,
        },
    }
