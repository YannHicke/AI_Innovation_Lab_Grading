from __future__ import annotations

import json
from typing import Any, Dict, Union

try:  # pragma: no cover - optional dependency guard
    from json_repair import repair_json
except Exception:  # pragma: no cover - gracefully handle missing package
    repair_json = None

ANTHROPIC_STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"


def parse_llm_json(payload: Union[str, Dict[str, Any], list]) -> Dict[str, Any]:
    """Attempt to coerce LLM output into valid JSON."""

    if isinstance(payload, (dict, list)):
        return payload

    def _load(data: str) -> Dict[str, Any]:
        return json.loads(data)

    try:
        return _load(payload)
    except json.JSONDecodeError:
        trimmed = payload.strip()

    # Handle ```json fenced outputs
    if trimmed.startswith("```") and trimmed.endswith("```"):
        inner = trimmed.strip("` \n")
        try:
            return _load(inner)
        except json.JSONDecodeError:
            pass

    # Entire payload might be a JSON array
    if trimmed.startswith("[") and trimmed.endswith("]"):
        try:
            return _load(trimmed)
        except json.JSONDecodeError:
            pass

    # If the LLM returned surrounding prose, grab the first {...} block
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = trimmed[start : end + 1]
        try:
            return _load(candidate)
        except json.JSONDecodeError:
            pass

    # Fall back to automatic repair if the dependency is installed
    if repair_json is not None:  # pragma: no cover - requires optional package
        try:
            fixed = repair_json(trimmed)
            return _load(fixed)
        except json.JSONDecodeError:
            pass

    # Last resort: raise the original error for FastAPI exception handling
    raise json.JSONDecodeError("Unable to decode LLM JSON payload.", trimmed, 0)


def resolve_model_for_provider(settings: Any, provider: str) -> str:
    """Pick the LLM model based on provider with sensible defaults."""

    provider_normalized = (provider or "").strip().lower()
    fallback = (settings.llm_model or "").strip()
    if provider_normalized == "anthropic":
        return (settings.llm_model_anthropic or fallback or "").strip()
    return (settings.llm_model_openai or fallback or "").strip()


def flatten_message_content(content: Any) -> str:
    """Normalize OpenAI/Anthropic message content into a simple string."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if hasattr(content, "text"):
        try:
            text_value = content.text  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - best effort for SDK objects
            text_value = None
        if text_value is not None:
            return flatten_message_content(text_value)
    if hasattr(content, "value"):
        try:
            value = content.value  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - best effort for SDK objects
            value = None
        if value is not None:
            return flatten_message_content(value)
    if hasattr(content, "model_dump"):
        try:
            dumped = content.model_dump()
            return flatten_message_content(dumped)
        except Exception:
            pass
    if isinstance(content, (bytes, bytearray)):
        return content.decode("utf-8", errors="ignore")
    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for entry in content:
            parts.append(flatten_message_content(entry))
        return "".join(filter(None, parts))
    if isinstance(content, dict):
        # Typical OpenAI SDK objects expose {'type': 'output_text', 'text': '...'}
        for key in ("text", "value", "content"):
            text_value = content.get(key)
            if isinstance(text_value, (str, bytes, bytearray, list, tuple, dict)):
                return flatten_message_content(text_value)
        # As a fallback, stringify the dict itself
        return json.dumps(content)
    # OpenAIObject exposes `.model_dump()` so fall back to str()
    return str(content)


def extract_message_payload(message: Any) -> str:
    """Extract the best-effort textual payload from an SDK message object."""

    parsed = getattr(message, "parsed", None)
    if parsed is None:
        parsed_text = ""
    elif isinstance(parsed, (dict, list)):
        parsed_text = json.dumps(parsed)
    else:
        parsed_text = str(parsed)
    if parsed_text:
        return parsed_text

    content = getattr(message, "content", None)
    text = flatten_message_content(content)
    if text:
        return text

    if hasattr(message, "model_dump"):
        try:
            dumped = message.model_dump()
            dumped_text = flatten_message_content(dumped.get("content"))
            if dumped_text:
                return dumped_text
            return json.dumps(dumped)
        except Exception:
            pass

    if isinstance(parsed, str):
        return parsed
    # Absolute last resort: stringified message object
    return str(message)


def anthropic_message_call(client: Any, **kwargs: Any) -> Any:
    """Call the correct Anthropics endpoint (beta vs stable)."""

    beta_client = getattr(client, "beta", None)
    if beta_client and hasattr(beta_client, "messages"):
        return beta_client.messages.create(**kwargs)
    return client.messages.create(**kwargs)
