from __future__ import annotations

from typing import Any, Dict, List

PROMPT_PLACEHOLDER = "[Transcript will be inserted here]"


def build_preview_prompt(item: Dict[str, Any]) -> str:
    """Render a minimal preview prompt for educators showing only the description."""
    description = item.get("description") or ""
    return f"Description: {description}"


def build_item_prompt(item: Dict[str, Any], transcript_text: str, rubric_type: str) -> str:
    """Render the per-criterion scoring prompt shared by preview + scoring paths."""
    description = item.get("description") or ""
    metadata = item.get("metadata") or {}
    levels = metadata.get("performance_levels") or []
    checklist_required = metadata.get("checklist_required")

    lines: List[str] = [
        "You are an impartial assessor of clinical interview skills. "
        "Evaluate the transcript based on the criterion. "
        "Provide a numeric score, a brief justification, and evidence in the form of verbatim quotes from the transcript. "
        "Do not assume or invent content not present in the transcript.",
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
        "\nReturn ONLY JSON with the keys 'evaluation' -> {'score': number, 'justification': string, 'evidence': string, 'actionable suggestions': string}."
    )
    lines.append("\nTranscript:\n" + transcript_text.strip())
    return "\n".join(lines)
