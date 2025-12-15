from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any, Dict, List

import logging
from openai import OpenAI
from anthropic import Anthropic
from pypdf import PdfReader

from ..config import get_settings
from .llm_utils import (
    resolve_model_for_provider,
    extract_message_payload,
    normalize_provider,
    parse_llm_json,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a JSON-only API that extracts rubric criteria from documents.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no markdown, no code blocks
2. Start your response with { and end with }
3. Do not wrap the JSON in ```json``` or any other formatting

Required JSON structure:
{
  "rubric_title": "string",
  "rubric_summary": "string",
  "max_total_score": number,
  "rubric_type": "analytic|holistic|single_point|checklist|hybrid",
  "criteria": [
    {
      "name": "string",
      "description": "string",
      "max_score": number,
      "item_type": "criterion",
      "weight": null,
      "metadata": {}
    }
  ]
}"""

RUBRIC_TYPES = ["analytic", "holistic", "single_point", "checklist", "hybrid"]

RUBRIC_TEXT_SCHEMA: Dict[str, Any] = {
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
                    "item_type": {"type": ["string", "null"]},
                    "weight": {"type": ["number", "null"]},
                    "metadata": {
                        "type": ["object", "null"],
                        "properties": {
                            "performance_levels": {
                                "type": ["array", "null"],
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": ["string", "null"]},
                                        "description": {"type": ["string", "null"]},
                                        "score": {"type": ["number", "null"]},
                                    },
                                    "additionalProperties": True,
                                },
                            },
                            "checklist_required": {"type": ["boolean", "null"]},
                            "single_point": {
                                "type": ["object", "null"],
                                "properties": {
                                    "target_description": {"type": ["string", "null"]},
                                    "exceeds_description": {"type": ["string", "null"]},
                                    "below_description": {"type": ["string", "null"]},
                                },
                                "additionalProperties": True,
                            },
                            "keywords": {
                                "type": ["array", "null"],
                                "items": {"type": "string"},
                            },
                        },
                        "additionalProperties": True,
                    },
                },
                "required": [
                    "name",
                    "description",
                    "max_score",
                    "item_type",
                    "weight",
                    "metadata",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rubric_title", "rubric_summary", "max_total_score", "rubric_type", "criteria"],
    "additionalProperties": False,
}

OPENAI_RUBRIC_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "rubric_extraction",
        "strict": True,
        "schema": RUBRIC_TEXT_SCHEMA,
    },
}


class RubricParsingError(RuntimeError):
    """Raised when the LLM cannot create a structured rubric."""


@dataclass
class LLMRubricParser:
    """Wrapper around the LLM client for rubric extraction."""

    client: Any  # OpenAI or Anthropic
    model: str
    temperature: float
    max_output_tokens: int
    provider: str

    def parse(self, raw_text: str) -> Dict[str, Any]:
        if not raw_text or not raw_text.strip():
            raise RubricParsingError("Rubric text is empty.")

        user_message = f"Extract rubric criteria as JSON:\n\n{raw_text.strip()}"

        try:
            if self.provider == "anthropic":
                # Anthropic doesn't support response_format like OpenAI
                # Instead, we rely on the system prompt to enforce JSON output
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_output_tokens,
                    temperature=self.temperature,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                )
                stop_reason = getattr(response, "stop_reason", None)
                if stop_reason == "max_tokens":
                    raise RubricParsingError(
                        f"LLM response truncated (stop_reason=max_tokens). Increase APP_LLM_MAX_OUTPUT_TOKENS (current {self.max_output_tokens})."
                    )
                payload = response.content[0].text if response.content else response
            else:  # openai
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_output_tokens,
                    response_format=OPENAI_RUBRIC_RESPONSE_FORMAT,
                )
                message = response.choices[0].message
                refusal = getattr(message, "refusal", None)
                if refusal:
                    raise RubricParsingError(f"LLM refused to parse rubric: {refusal}")
                # If the SDK already parsed JSON for us, return it directly.
                parsed_field = getattr(message, "parsed", None)
                if isinstance(parsed_field, (dict, list)):
                    return parsed_field
                try:
                    finish_reason = response.choices[0].finish_reason
                except Exception:
                    finish_reason = None
                logger.info("Rubric parse finish_reason=%s usage=%s", finish_reason, getattr(response, "usage", None))
                if finish_reason == "length":
                    raise RubricParsingError(
                        f"LLM response truncated (finish_reason=length). Increase APP_LLM_MAX_OUTPUT_TOKENS (current {self.max_output_tokens})."
                    )
                payload = extract_message_payload(message)
        except Exception as exc:  # pragma: no cover - network failure pass-through
            # Check for rate limit errors
            error_message = str(exc).lower()
            if "429" in error_message or "rate" in error_message or "too many requests" in error_message:
                raise RubricParsingError(
                    "Rate limit exceeded. Please wait a minute before uploading another rubric, or switch to a different LLM provider in settings."
                ) from exc
            raise RubricParsingError(f"LLM request failed: {exc}") from exc

        if payload in (None, "", []):
            raise RubricParsingError("LLM returned an empty response.")

        try:
            return parse_llm_json(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            snippet = str(payload)[:500] if payload is not None else "<empty payload>"
            logger.error("Failed to decode LLM JSON; payload snippet: %s", snippet)
            raise RubricParsingError(f"LLM returned invalid JSON: {exc}") from exc


def pdf_bytes_to_text(data: bytes) -> str:
    """Extract raw text from an uploaded PDF."""

    reader = PdfReader(BytesIO(data))
    contents = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(contents)


def _get_llm_parser(provider_override: str | None) -> LLMRubricParser:
    settings = get_settings()
    provider = normalize_provider(provider_override, settings)
    return _build_llm_parser(provider)


@lru_cache()
def _build_llm_parser(provider: str) -> LLMRubricParser:
    settings = get_settings()

    model = resolve_model_for_provider(settings, provider)
    if not model:
        raise RubricParsingError(
            "LLM model is not configured (set APP_LLM_MODEL or provider-specific APP_LLM_MODEL_OPENAI / APP_LLM_MODEL_ANTHROPIC)."
        )

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RubricParsingError("Anthropic API key is not configured (APP_ANTHROPIC_API_KEY).")
        # Allow 2 retries with exponential backoff for rate limits
        client_kwargs: Dict[str, Any] = {"api_key": settings.anthropic_api_key, "max_retries": 2}
        if settings.anthropic_base_url:
            client_kwargs["base_url"] = settings.anthropic_base_url
        client = Anthropic(**client_kwargs)
    else:  # openai
        if not settings.openai_api_key:
            raise RubricParsingError("OpenAI API key is not configured (APP_OPENAI_API_KEY).")
        client_kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.llm_base_url:
            client_kwargs["base_url"] = settings.llm_base_url
        client = OpenAI(**client_kwargs)

    return LLMRubricParser(
        client=client,
        model=model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        provider=provider,
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


def parse_rubric(raw_text: str, provider: str | None = None) -> dict:
    """Use an LLM to transform rubric text into structured JSON."""

    llm_parser = _get_llm_parser(provider)
    result = llm_parser.parse(raw_text)

    criteria_payload = _resolve_criteria_payload(result)
    if not criteria_payload:
        raise RubricParsingError("LLM response did not include any criteria.")

    rubric_type = _normalize_rubric_type(result.get("rubric_type"))
    levels = _normalize_levels(result.get("holistic_levels") or [], prefix="overall")

    criteria: List[dict] = []
    for idx, item in enumerate(criteria_payload, start=1):
        name = (item.get("name") or f"Criterion {idx}").strip()
        description = (item.get("description") or "").strip() or None
        max_score_raw = item.get("max_score")
        # For checklist items, max_score can be None; default to 1.0
        if max_score_raw is None:
            max_score = 1.0
        else:
            max_score = _coerce_float(max_score_raw)
        item_type = (item.get("item_type") or "criterion").strip().lower()
        weight_raw = item.get("weight")
        weight = _coerce_float(weight_raw) if weight_raw is not None else None
        metadata_payload = item.get("metadata")
        if not isinstance(metadata_payload, dict):
            metadata_payload = {}

        metadata: Dict[str, Any] = {}
        keywords_source = metadata_payload.get("keywords")
        if keywords_source is None:
            keywords_source = item.get("keywords")
        keywords = _clean_keywords(keywords_source)
        if keywords:
            metadata["keywords"] = keywords
        single_point_source = metadata_payload.get("single_point")
        if not isinstance(single_point_source, dict):
            single_point_source = {}
        single_point = {
            "target_description": _clean_text(
                single_point_source.get("target_description") or item.get("target_description")
            ),
            "exceeds_description": _clean_text(
                single_point_source.get("exceeds_description") or item.get("exceeds_description")
            ),
            "below_description": _clean_text(
                single_point_source.get("below_description") or item.get("below_description")
            ),
        }
        if any(single_point.values()):
            metadata["single_point"] = single_point
        checklist_required = metadata_payload.get("checklist_required")
        if checklist_required is None:
            checklist_required = item.get("checklist_required", False)
        if item_type == "checklist" or rubric_type == "checklist":
            metadata["checklist_required"] = bool(checklist_required)
        perf_source = metadata_payload.get("performance_levels")
        if perf_source is None:
            perf_source = item.get("performance_levels")
        if not isinstance(perf_source, list):
            perf_source = []
        perf_levels = _normalize_levels(
            perf_source, prefix=f"{name.lower().replace(' ', '_')}_level"
        )
        if perf_levels:
            metadata["performance_levels"] = perf_levels

        criterion_payload = {
            "name": name,
            "description": description,
            "max_score": max_score,
            "item_type": item_type,
            "weight": weight,
            "metadata": metadata,
        }

        criteria.append(criterion_payload)

    declared_total = result.get("max_total_score")
    max_total_score = _coerce_float(declared_total) if declared_total is not None else sum(c["max_score"] for c in criteria)

    summary_source = (result.get("rubric_summary") or "").strip()
    if not summary_source:
        summary_source = raw_text.strip().replace("\n", " ")

    title = (result.get("rubric_title") or "Uploaded Rubric").strip()

    return {
        "title": title or "Uploaded Rubric",
        "summary": summary_source[:400],
        "criteria": criteria,
        "max_total_score": max_total_score,
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


def _resolve_criteria_payload(result: Any) -> List[Dict[str, Any]]:
    """Handle multiple possible schema variants returned by the LLM."""

    if isinstance(result, list):
        return [entry for entry in result if isinstance(entry, dict)]

    if not isinstance(result, dict):
        return []

    candidate_keys = [
        "criteria",
        "rubric_items",
        "items",
        "rubricCriteria",
        "rubric_items_list",
    ]

    for key in candidate_keys:
        payload = result.get(key)
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]

    # Sometimes the model nests the rubric inside another key
    nested = result.get("rubric") or result.get("data")
    if isinstance(nested, dict):
        return _resolve_criteria_payload(nested)

    return []
