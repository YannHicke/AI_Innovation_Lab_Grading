from __future__ import annotations

from typing import Any, Dict, List

PROMPT_PLACEHOLDER = "[Transcript will be inserted here]"


def build_item_prompt(item: Dict[str, Any], transcript_text: str, rubric_type: str) -> str:
    """Render the per-criterion scoring prompt shared by preview + scoring paths."""
    description = item.get("description") or ""
    metadata = item.get("metadata") or {}
    levels = metadata.get("performance_levels") or []
    checklist_required = metadata.get("checklist_required")

    lines: List[str] = [
        "You are an impartial assessor of clinical interview skills. You will receive:",
        "All rubric criterion (including its name, description, and scoring scale).",
        "",
        "A cleaned transcript.",
        "",
        "Your tasks:",
        "Score only this specific criterion at a time before moving to the next.",
        "",
        "Provide:",
        "- The numeric score.",
        "- A brief justification (1–2 sentences).",
        "- Evidence taken directly from the transcript as an exact quote.",
        "",
        "Rules:",
        "- Do not reference any other criteria.",
        "- Do not invent or assume transcript content.",
        "- Evidence must be a verbatim quotation from the transcript.",
        "",
        f"Rubric item: {item['name']}",
        f"Description: {description}",
        f"Maximum score: {item['max_score']}",
        f"Rubric type: {rubric_type}",
    ]

    if checklist_required is not None:
        lines.append(f"Checklist requirement: {'required' if checklist_required else 'optional'}")

    if levels:
        lines.append("\nScoring guidance:")
        for level in levels:
            score_value = level.get("score")
            label = level.get("label") or f"Score {score_value}"
            detail = level.get("description") or ""
            lines.append(f"- Score {score_value}: {detail} ({label})")

    lines.append(
        "\nReturn ONLY JSON with the keys 'evaluation' -> {'score': number, 'justification': string}."
    )
    lines.append("\nTranscript:\n" + transcript_text.strip())
    return "\n".join(lines)
