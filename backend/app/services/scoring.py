from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List

from openai import OpenAI
from anthropic import Anthropic

from ..config import get_settings
from .prompt_builder import build_item_prompt
from .llm_utils import (
    ANTHROPIC_STRUCTURED_OUTPUTS_BETA,
    anthropic_message_call,
    extract_message_payload,
    parse_llm_json,
    resolve_model_for_provider,
)

logger = logging.getLogger(__name__)

DEFAULT_RUBRIC_TYPE = "analytic"

ITEM_SYSTEM_PROMPT = (
    "You are an impartial assessor of medical interview skills. "
    "For each rubric item evaluate only that dimension, apply the provided scoring guidance, "
    "quote the transcript directly, and return JSON with a numeric score and justification."
)

SCORING_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "evaluation": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "justification": {"type": "string"},
            },
            "required": ["score", "justification"],
            "additionalProperties": False,
        }
    },
    "required": ["evaluation"],
    "additionalProperties": False,
}

OPENAI_SCORING_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "single_rubric_item_scoring",
        "strict": True,
        "schema": SCORING_ITEM_SCHEMA,
    },
}


class ScoringError(RuntimeError):
    """Raised when rubric scoring fails."""


@dataclass
class LLMScoringClient:
    client: Any  # OpenAI or Anthropic
    model: str
    temperature: float
    max_output_tokens: int
    provider: str

    def score_item(self, *, prompt: str) -> Dict[str, Any]:
        logger.debug("LLM scoring prompt input: %s", prompt[:2000])
        try:
            if self.provider == "anthropic":
                response = anthropic_message_call(
                    self.client,
                    model=self.model,
                    max_tokens=self.max_output_tokens,
                    temperature=self.temperature,
                    system=ITEM_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    betas=[ANTHROPIC_STRUCTURED_OUTPUTS_BETA],
                    output_format={"type": "json_schema", "schema": SCORING_ITEM_SCHEMA},
                )
                payload = response.content[0].text
                logger.info(
                    "LLM scoring response for prompt hash=%s: usage=%s",
                    hash(prompt),
                    response.usage,
                )
            else:  # openai
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": ITEM_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_output_tokens,
                    response_format=OPENAI_SCORING_RESPONSE_FORMAT,
                )
                message = response.choices[0].message
                refusal = getattr(message, "refusal", None)
                if refusal:
                    raise ScoringError(f"LLM refused to score criterion: {refusal}")
                parsed_field = getattr(message, "parsed", None)
                if isinstance(parsed_field, (dict, list)):
                    return parsed_field
                payload = extract_message_payload(message)
                logger.info(
                    "LLM scoring response for prompt hash=%s: usage=%s",
                    hash(prompt),
                    response.usage,
                )
        except Exception as exc:  # pragma: no cover - network failure pass-through
            raise ScoringError(f"LLM scoring request failed: {exc}") from exc

        try:
            return parse_llm_json(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise ScoringError(f"LLM scoring returned invalid JSON: {exc}") from exc


def score_criteria(
    criteria: List[dict],
    transcript_text: str,
    rubric_type: str = DEFAULT_RUBRIC_TYPE,
    provider: str | None = None,
) -> dict:
    if not criteria:
        raise ScoringError("At least one rubric criterion is required for scoring.")
    if not transcript_text or not transcript_text.strip():
        raise ScoringError("Transcript text is empty.")

    rubric_payload: List[Dict[str, Any]] = []
    for idx, item in enumerate(criteria, start=1):
        payload_item = {
            "rubric_item_id": item.get("rubric_item_id") or item.get("id") or f"criterion_{idx}",
            "name": (item.get("name") or f"Criterion {idx}").strip(),
            "description": (item.get("description") or "").strip() or None,
            "item_type": (item.get("item_type") or "criterion").strip().lower(),
            "max_score": float(item.get("max_score") or 0.0) or 1.0,
            "weight": float(item["weight"]) if item.get("weight") is not None else None,
            "metadata": item.get("metadata") or {},
        }
        rubric_payload.append(payload_item)

    scorer = _get_llm_scorer(provider)
    normalized_scores: List[Dict[str, Any]] = []
    for item in rubric_payload:
        prompt = build_item_prompt(item, transcript_text, rubric_type or DEFAULT_RUBRIC_TYPE)
        logger.info("Scoring prompt for item %s (%s): %s", item["rubric_item_id"], item["name"], prompt)
        result = scorer.score_item(prompt=prompt)
        evaluation = result.get("evaluation") or result
        score_value = float(evaluation.get("score", 0.0))
        clamped_score = max(0.0, min(score_value, item["max_score"]))
        justification = (evaluation.get("justification") or "").strip()
        if not justification:
            justification = "No justification provided."
        normalized_scores.append(
            {
                "rubric_item_id": item["rubric_item_id"],
                "item_type": item["item_type"],
                "name": item["name"],
                "description": item["description"],
                "score": round(clamped_score, 2),
                "max_score": item["max_score"],
                "feedback": justification,
                "evidence": justification,
                "justification": justification,
            }
        )

    total_score = round(sum(item["score"] for item in normalized_scores), 2)
    max_total_score = round(sum(item["max_score"] for item in normalized_scores), 2)
    percent = (total_score / max_total_score) * 100 if max_total_score else 0.0
    band = performance_band(percent)
    summary = f"Overall score {total_score}/{max_total_score} ({percent:.1f}% - {band})."

    strengths = [
        f"{item['name']}: {item['score']}/{item['max_score']}"
        for item in sorted(
            normalized_scores,
            key=lambda entry: entry["score"] / entry["max_score"] if entry["max_score"] else 0.0,
            reverse=True,
        )
        if item["score"] >= 0.8 * item["max_score"]
    ][:3]
    areas = [
        f"{item['name']}: {item['score']}/{item['max_score']}"
        for item in sorted(
            normalized_scores,
            key=lambda entry: entry["score"] / entry["max_score"] if entry["max_score"] else 0.0,
        )
        if item["score"] <= 0.6 * item["max_score"]
    ][:3]

    narrative = (
        f"{band} overall performance. "
        f"Strengths: {', '.join(strengths) if strengths else 'none identified'}. "
        f"Areas for development: {', '.join(areas) if areas else 'none identified'}."
    )

    return {
        "criterion_scores": normalized_scores,
        "total_score": total_score,
        "max_total_score": max_total_score,
        "performance_band": band,
        "performance_level": band,
        "summary": summary,
        "key_strengths": strengths,
        "areas_for_development": areas,
        "narrative_feedback": narrative,
        "rubric_type": rubric_type or DEFAULT_RUBRIC_TYPE,
    }


def performance_band(percent: float) -> str:
    if percent >= 90:
        return "Outstanding"
    if percent >= 80:
        return "Strong"
    if percent >= 65:
        return "Competent"
    if percent >= 50:
        return "Developing"
    return "Needs Support"


def _get_llm_scorer(provider_override: str | None) -> LLMScoringClient:
    provider = _normalize_provider(provider_override)
    return _build_llm_scorer(provider)


@lru_cache()
def _build_llm_scorer(provider: str) -> LLMScoringClient:
    settings = get_settings()

    model = resolve_model_for_provider(settings, provider)
    if not model:
        raise ScoringError(
            "LLM model is not configured (set APP_LLM_MODEL or provider-specific APP_LLM_MODEL_OPENAI / APP_LLM_MODEL_ANTHROPIC)."
        )

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ScoringError("Anthropic API key is not configured (APP_ANTHROPIC_API_KEY).")
        client = Anthropic(api_key=settings.anthropic_api_key)
    else:  # openai
        if not settings.openai_api_key:
            raise ScoringError("OpenAI API key is not configured (APP_OPENAI_API_KEY).")
        client_kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.llm_base_url:
            client_kwargs["base_url"] = settings.llm_base_url
        client = OpenAI(**client_kwargs)

    return LLMScoringClient(
        client=client,
        model=model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        provider=provider,
    )


def _build_item_prompt(item: Dict[str, Any], transcript_text: str, rubric_type: str) -> str:
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
        "Provide:",
        "- The numeric score.",
        "- A brief justification (1–2 sentences).",
        "- Evidence taken directly from the transcript as an exact quote.",
        # // is this too difficult for an llm to do all at once, or is it okay
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
    # handle any accomodation of those like in the dashboard timmy wants about student growth maybe in this area ere of outputting score justification and evidecne
    lines.append("\nTranscript:\n" + transcript_text.strip())
    return "\n".join(lines)
