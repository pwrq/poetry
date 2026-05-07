"""
Judge utilities — score parsing and consensus checking.
Used by deliberation.py.
"""
from __future__ import annotations
import json
import re
from app.models import RoundScore, Poem


def _normalise_score(parsed: dict, name_to_id: dict[str, str]) -> dict | None:
    """Resolve contestant_id and clamp score values. Returns None if unresolvable."""
    raw = str(parsed.get("contestant_id", "")).lower()
    if raw in name_to_id:
        parsed["contestant_id"] = name_to_id[raw]
    for key in ("on_topic", "originality", "artistic_value"):
        val = parsed.get(key)
        if isinstance(val, (int, float)):
            parsed[key] = max(1.0, min(10.0, float(val)))
        else:
            parsed[key] = 5.0
    return parsed


def _parse_scores(text: str, poems: list[Poem]) -> tuple[str, list[dict]]:
    """Extract discussion text and JSON scores from a judge LLM response.

    LLMs naturally use display names as contestant_id instead of internal IDs.
    Build a map that accepts both and normalises to the real contestant_id.

    Two-pass strategy:
    1. Strip code fences, then scan line-by-line for single-line JSON objects.
    2. Regex fallback for multi-line JSON if fewer scores than poems were found.
    """
    # Map lowercase display-name words → real contestant_id
    name_to_id: dict[str, str] = {}
    for p in poems:
        name_to_id[p.contestant_id.lower()] = p.contestant_id
        name_to_id[p.contestant_name.lower()] = p.contestant_id
        for word in p.contestant_name.lower().split():
            if word not in name_to_id:
                name_to_id[word] = p.contestant_id

    # Strip markdown code fences (```json ... ```)
    clean_text = re.sub(r'```\w*\n?', '', text)

    lines = clean_text.strip().split("\n")
    json_lines: list[dict] = []
    discussion_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{") and "contestant_id" in stripped:
            try:
                parsed = json.loads(stripped.rstrip(",; "))
                result = _normalise_score(parsed, name_to_id)
                if result is not None:
                    json_lines.append(result)
                    continue
            except json.JSONDecodeError:
                pass
        discussion_lines.append(line)

    # Fallback: regex extraction for multi-line JSON when scores are missing
    if len(json_lines) < len(poems):
        found_ids = {j.get("contestant_id") for j in json_lines}
        for m in re.finditer(r'\{[^{}]*"contestant_id"[^{}]*\}', clean_text, re.DOTALL):
            try:
                parsed = json.loads(m.group())
                result = _normalise_score(parsed, name_to_id)
                if result and result.get("contestant_id") not in found_ids:
                    json_lines.append(result)
                    found_ids.add(result.get("contestant_id"))
            except json.JSONDecodeError:
                pass

    return "\n".join(discussion_lines).strip(), json_lines


def check_consensus(state: dict, all_proposed: list[list[dict]]) -> tuple[bool, list[RoundScore]]:
    """Check if all judges agree within tolerance on each score.
    Returns (consensus_reached, final_scores).
    """
    poems = state.get("poems_this_round", [])
    if not all_proposed or not poems:
        return True, []

    final: list[RoundScore] = []
    for poem in poems:
        cid = poem.contestant_id
        scores_for = []
        for proposed in all_proposed:
            for s in proposed:
                if s.get("contestant_id") == cid:
                    scores_for.append(s)
                    break

        if not scores_for:
            final.append(RoundScore(
                contestant_id=cid, contestant_name=poem.contestant_name,
                on_topic=5.0, originality=5.0, artistic_value=5.0, total=15.0,
            ))
            continue

        on_topics = [s.get("on_topic", 5.0) for s in scores_for]
        originals = [s.get("originality", 5.0) for s in scores_for]
        arts = [s.get("artistic_value", 5.0) for s in scores_for]

        on_i = round(sum(on_topics) / len(on_topics))
        orig_i = round(sum(originals) / len(originals))
        art_i = round(sum(arts) / len(arts))

        final.append(RoundScore(
            contestant_id=cid, contestant_name=poem.contestant_name,
            on_topic=float(on_i), originality=float(orig_i),
            artistic_value=float(art_i), total=float(on_i + orig_i + art_i),
        ))

    # Overall consensus: all poems must have low variance across judges
    all_agreed = True
    for poem in poems:
        cid = poem.contestant_id
        scores_for = []
        for proposed in all_proposed:
            for s in proposed:
                if s.get("contestant_id") == cid:
                    scores_for.append(s)
                    break
        if not scores_for:
            continue
        on_topics = [s.get("on_topic", 5.0) for s in scores_for]
        originals = [s.get("originality", 5.0) for s in scores_for]
        arts = [s.get("artistic_value", 5.0) for s in scores_for]
        if (max(on_topics) - min(on_topics) > 1.5 or
                max(originals) - min(originals) > 1.5 or
                max(arts) - min(arts) > 1.5):
            all_agreed = False
            break

    return all_agreed, final
