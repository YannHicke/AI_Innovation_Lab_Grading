from __future__ import annotations

from statistics import mean
from typing import Dict, List

import numpy as np

POSITIVE_KEYWORDS: Dict[str, List[str]] = {
    "Empathy": ["sorry", "understand", "appreciate", "concern", "feel"],
    "Clinical Reasoning": ["diagnosis", "plan", "assessment", "differential", "treatment"],
    "Education": ["explain", "teach", "information", "instructions", "step"],
    "Communication": ["thank", "clarify", "follow up", "summary", "recap"],
}

NEGATIVE_KEYWORDS = ["angry", "frustrated", "upset", "confused"]


def keyword_hits(text: str, keywords: List[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(word) for word in keywords)


def score_criteria(criteria: List[dict], transcript_text: str) -> dict:
    transcript = transcript_text.lower()
    criterion_scores = []

    for item in criteria:
        name = item["name"]
        max_score = float(item.get("max_score", 5.0))
        base_keywords = POSITIVE_KEYWORDS.get(name, POSITIVE_KEYWORDS.get("Communication"))
        hits = keyword_hits(transcript, base_keywords)
        penalty = keyword_hits(transcript, NEGATIVE_KEYWORDS)
        raw_score = max(0.0, hits - 0.3 * penalty)
        scaled = min(max_score, (raw_score / max(1.0, hits or 1)) * max_score if hits else max_score * 0.4)
        feedback = _build_feedback(name, hits, penalty)
        criterion_scores.append(
            {
                "name": name,
                "description": item.get("description"),
                "score": round(scaled, 2),
                "max_score": max_score,
                "feedback": feedback,
            }
        )

    total_score = round(sum(item["score"] for item in criterion_scores), 2)
    max_total = round(sum(item["max_score"] for item in criterion_scores), 2)
    percent = (total_score / max_total) * 100 if max_total else 0
    band = performance_band(percent)
    summary = build_summary(criterion_scores, percent)

    return {
        "criterion_scores": criterion_scores,
        "total_score": total_score,
        "max_total_score": max_total,
        "performance_band": band,
        "summary": summary,
    }


def performance_band(percent: float) -> str:
    if percent >= 90:
        return "Outstanding"
    if percent >= 75:
        return "Strong"
    if percent >= 60:
        return "Competent"
    return "Needs Support"


def build_summary(scores: List[dict], percent: float) -> str:
    top_strength = max(scores, key=lambda s: s["score"], default=None)
    needs_support = min(scores, key=lambda s: s["score"], default=None)
    parts = [
        f"Overall performance is {percent:.1f}% ({performance_band(percent)}).",
    ]
    if top_strength:
        parts.append(f"Strength: {top_strength['name']} ({top_strength['score']}/{top_strength['max_score']}).")
    if needs_support and needs_support != top_strength:
        parts.append(
            f"Focus area: {needs_support['name']} ({needs_support['score']}/{needs_support['max_score']})."
        )
    return " ".join(parts)


def _build_feedback(name: str, hits: int, penalty: int) -> str:
    if hits == 0:
        return f"No clear evidence of {name.lower()} was detected. Consider adding explicit statements."
    if penalty:
        return f"{name} moments were detected, but tone risks undermining impact. Reduce language that signals frustration."
    return f"Reliable {name.lower()} language detected. Keep reinforcing this behaviour."
