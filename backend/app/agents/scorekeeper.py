"""
Scorekeeper utility — shared helper used by tally_scores and crown_winner tools.
"""
from __future__ import annotations
from app.models import RoundScore, CumulativeScore


def _cumulative(all_scores: list[RoundScore]) -> list[CumulativeScore]:
    """Compute cumulative standings from all round scores."""
    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    for s in all_scores:
        totals[s.contestant_id] = totals.get(s.contestant_id, 0.0) + s.total
        names[s.contestant_id] = s.contestant_name

    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    result: list[CumulativeScore] = []
    rank = 1
    for i, (cid, tot) in enumerate(ranked):
        if i > 0 and tot < ranked[i - 1][1]:
            rank = i + 1  # skip positions for tied group (competition ranking)
        result.append(CumulativeScore(
            contestant_id=cid,
            contestant_name=names[cid],
            total=tot,
            rank=rank,
        ))
    return result
