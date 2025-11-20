from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any, Dict, List

from openai import OpenAI
from pypdf import PdfReader

from ..config import get_settings


SYSTEM_PROMPT = (
    "You are an assistant that converts free-form grading rubrics into structured JSON. "
    "Extract every criterion you can find without inventing extra ones. "
    "Only return valid JSON that matches the provided schema."
)

RUBRIC_TYPES = ["analytic", "holistic", "single_point", "checklist", "hybrid"]

RUBRIC_TEXT_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "name": "rubric_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "rubric_title": {"type": "string"},
            "rubric_summary": {"type": "string"},
            "max_total_score": {"type": "number"},
            "rubric_type": {"type": "string", "enum": RUBRIC_TYPES},
            "criteria": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": ["string", "null"]},
                        "max_score": {"type": "number"},
                    },
                    "required": [
                        "name",
                        "description",
                        "max_score",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["rubric_title", "rubric_summary", "max_total_score", "rubric_type", "criteria"],
        "additionalProperties": False,
    },
}


class RubricParsingError(RuntimeError):
    """Raised when the LLM cannot create a structured rubric."""


@dataclass
class LLMRubricParser:
    """Wrapper around the OpenAI client for rubric extraction."""

    client: OpenAI
    model: str
    temperature: float
    max_output_tokens: int

    def parse(self, raw_text: str) -> Dict[str, Any]:
        if not raw_text or not raw_text.strip():
            raise RubricParsingError("Rubric text is empty.")

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=(
                    "Convert the following rubric into JSON. "
                    "Infer missing numeric maxima conservatively and never invent extra criteria.\n\n"
                    f"RUBRIC SOURCE:\n{raw_text.strip()}"
                ),
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                text={"format": RUBRIC_TEXT_FORMAT},
            )
        except Exception as exc:  # pragma: no cover - network failure pass-through
            raise RubricParsingError(f"LLM request failed: {exc}") from exc

        payload = _extract_output_text(response)

        try:
            return _safe_json_loads(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise RubricParsingError(f"LLM returned invalid JSON: {exc}") from exc


def pdf_bytes_to_text(data: bytes) -> str:
    """Extract raw text from an uploaded PDF."""

    reader = PdfReader(BytesIO(data))
    contents = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(contents)


@lru_cache()
def _get_llm_parser() -> LLMRubricParser:
    settings = get_settings()
    if settings.llm_provider != "openai":  # pragma: no cover - single provider guard
        raise RubricParsingError(f"Unsupported LLM provider: {settings.llm_provider}")
    if not settings.openai_api_key:
        raise RubricParsingError("OpenAI API key is not configured (APP_OPENAI_API_KEY).")
    if not settings.llm_model:
        raise RubricParsingError("LLM model is not configured (APP_LLM_MODEL).")

    client_kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.llm_base_url:
        client_kwargs["base_url"] = settings.llm_base_url

    client = OpenAI(**client_kwargs)
    return LLMRubricParser(
        client=client,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
    )


def _coerce_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise RubricParsingError(f"Expected numeric value, received: {value}") from exc
    raise RubricParsingError(f"Expected numeric value, received: {value}")


def parse_rubric(raw_text: str) -> dict:
    """Use an LLM to transform rubric text into structured JSON."""

    llm_parser = _get_llm_parser()
    result = llm_parser.parse(raw_text)

    criteria_payload: List[Dict[str, Any]] = result.get("criteria") or []
    if not criteria_payload:
        raise RubricParsingError("LLM response did not include any criteria.")

    rubric_type = _normalize_rubric_type(result.get("rubric_type"))
    levels = _normalize_levels(result.get("holistic_levels") or [], prefix="overall")

    criteria: List[dict] = []
    for idx, item in enumerate(criteria_payload, start=1):
        name = (item.get("name") or f"Criterion {idx}").strip()
        description = (item.get("description") or "").strip() or None
        max_score = _coerce_float(item.get("max_score"))
        item_type = (item.get("item_type") or "criterion").strip().lower()
        weight_raw = item.get("weight")
        weight = _coerce_float(weight_raw) if weight_raw is not None else None
        metadata: Dict[str, Any] = {}
        keywords = _clean_keywords(item.get("keywords"))
        if keywords:
            metadata["keywords"] = keywords
        single_point = {
            "target_description": _clean_text(item.get("target_description")),
            "exceeds_description": _clean_text(item.get("exceeds_description")),
            "below_description": _clean_text(item.get("below_description")),
        }
        if any(single_point.values()):
            metadata["single_point"] = single_point
        if item_type == "checklist" or rubric_type == "checklist":
            metadata["checklist_required"] = bool(item.get("checklist_required", False))
        perf_levels = _normalize_levels(item.get("performance_levels") or [], prefix=f"{name.lower().replace(' ', '_')}_level")
        if perf_levels:
            metadata["performance_levels"] = perf_levels

        criteria.append(
            {
                "name": name,
                "description": description,
                "max_score": max_score,
                "item_type": item_type,
                "weight": weight,
                "metadata": metadata,
            }
        )

    declared_total = result.get("max_total_score")
    max_total = _coerce_float(declared_total) if declared_total is not None else sum(c["max_score"] for c in criteria)

    summary_source = (result.get("rubric_summary") or "").strip()
    if not summary_source:
        summary_source = raw_text.strip().replace("\n", " ")

    title = (result.get("rubric_title") or "Uploaded Rubric").strip()

    return {
        "title": title or "Uploaded Rubric",
        "summary": summary_source[:400],
        "criteria": criteria,
        "max_total": max_total,
        "rubric_type": rubric_type,
        "levels": levels,
    }


def _clean_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _clean_keywords(payload: Any) -> List[str] | None:
    if not isinstance(payload, (list, tuple)):
        return None
    keywords: List[str] = []
    for raw in payload:
        if raw is None:
            continue
        cleaned = str(raw).strip()
        if cleaned and cleaned not in keywords:
            keywords.append(cleaned)
    return keywords or None


def _normalize_levels(payload: Any, prefix: str = "level") -> List[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    levels: List[Dict[str, Any]] = []
    for idx, entry in enumerate(payload, start=1):
        if not isinstance(entry, dict):
            continue
        label = (entry.get("label") or f"Level {idx}").strip()
        description = _clean_text(entry.get("description"))
        score_raw = entry.get("score")
        score = _coerce_float(score_raw) if score_raw is not None else None
        level_key = (entry.get("level_key") or f"{prefix}_{idx}").strip()
        levels.append(
            {
                "level_key": level_key,
                "label": label,
                "description": description,
                "score": score,
            }
        )
    return levels


def _normalize_rubric_type(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in RUBRIC_TYPES:
            return normalized
    return "analytic"


def _extract_output_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if direct:
        return direct

    output = getattr(response, "output", None) or []
    fragments: List[str] = []
    for block in output:
        content = getattr(block, "content", None) or getattr(block, "output", None)
        if not content:
            continue
        for item in content:
            text = getattr(item, "text", None)
            if text:
                fragments.append(text)
            elif isinstance(item, dict) and item.get("text"):
                fragments.append(str(item["text"]))

    if not fragments:
        raise RubricParsingError("LLM response did not contain any text output.")

    return "\n".join(fragments)


def _safe_json_loads(payload: str) -> Dict[str, Any]:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        trimmed = payload.strip()
        if trimmed.startswith("```") and trimmed.endswith("```"):
            inner = trimmed.strip("` \n")
            return json.loads(inner)
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = trimmed[start : end + 1]
            return json.loads(candidate)
        raise
