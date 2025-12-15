from __future__ import annotations

from typing import Any, Iterable, List

from ..models import RubricItem
from ..schemas import GeneratedPrompt, RubricCriterionPreview, RubricParsingInfo
from .prompt_builder import build_preview_prompt


def scoring_payload_from_models(rubric_items: Iterable[RubricItem], fallback_max: float | None) -> List[dict]:
    """Serialize ORM rubric items into the structure required by the scorer."""
    resolved_fallback = fallback_max if fallback_max and fallback_max > 0 else 1.0
    payload: List[dict] = []
    for item in rubric_items:
        payload.append(
            {
                "rubric_item_id": item.id,
                "name": item.name,
                "description": item.description,
                "max_score": item.max_score if item.max_score is not None else resolved_fallback,
                "item_type": item.item_type,
                "weight": item.weight,
                "metadata": item.metadata_dict,
            }
        )
    return payload


def scoring_payload_from_payload(criteria: List[dict]) -> List[dict]:
    """Normalize parsed rubric criteria into a scorer-compatible structure."""
    payload: List[dict] = []
    for idx, criterion in enumerate(criteria, start=1):
        payload.append(
            {
                "rubric_item_id": criterion.get("rubric_item_id") or criterion.get("id") or f"criterion_{idx}",
                "name": criterion.get("name") or f"Criterion {idx}",
                "description": criterion.get("description"),
                "max_score": criterion.get("max_score") or 1.0,
                "item_type": (criterion.get("item_type") or "criterion").strip().lower(),
                "weight": criterion.get("weight"),
                "metadata": criterion.get("metadata") or {},
            }
        )
    return payload


def build_prompt_samples(scoring_items: List[dict]) -> List[GeneratedPrompt]:
    """Generate preview prompts showing only the description for educators."""
    prompts: List[GeneratedPrompt] = []
    for item in scoring_items:
        prompt_text = build_preview_prompt(item)
        prompts.append(GeneratedPrompt(criterion_name=item["name"], prompt_text=prompt_text))
    return prompts


def build_parsing_info(
    *,
    rubric_title: str,
    rubric_type: str,
    max_total_score: float,
    scoring_items: List[dict],
) -> RubricParsingInfo:
    """Assemble the RubricParsingInfo payload shared by both API endpoints."""
    criteria_previews: List[RubricCriterionPreview] = []
    for item in scoring_items:
        criteria_previews.append(
            RubricCriterionPreview(
                name=item["name"],
                description=item.get("description"),
                item_type=item.get("item_type") or "criterion",
                max_score=float(item.get("max_score") or 1.0),
                weight=item.get("weight"),
                metadata=item.get("metadata") or {},
            )
        )

    prompts = build_prompt_samples(scoring_items)

    return RubricParsingInfo(
        items_extracted=len(scoring_items),
        rubric_title=rubric_title,
        rubric_type=rubric_type,
        max_total_score=max_total_score,
        criteria_names=[item["name"] for item in scoring_items],
        criteria=criteria_previews,
        generated_prompts=prompts,
    )
