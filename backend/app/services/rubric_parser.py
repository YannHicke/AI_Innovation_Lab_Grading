from __future__ import annotations

import re
from io import BytesIO
from typing import List

from pypdf import PdfReader


def pdf_bytes_to_text(data: bytes) -> str:
    """Extract raw text from an uploaded PDF."""

    reader = PdfReader(BytesIO(data))
    contents = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(contents)


def parse_rubric(raw_text: str) -> dict:
    """Create a simple structured rubric from free-form text."""

    cleaned = re.sub(r"\s+", " ", raw_text).strip()
    title = cleaned.split(" ", 8)[0:8]
    title_text = "Rubric" if not title else " ".join(title)

    criteria: List[dict] = []
    for line in raw_text.splitlines():
        normalized = line.strip("• -*\u2022\t")
        if len(normalized) < 6:
            continue
        if normalized.lower().startswith("total"):
            continue

        match = re.match(r"(?P<name>[A-Za-z\s]+)(?::|-)?\s*(?P<rest>.*)", normalized)
        if not match:
            continue
        name = match.group("name").strip().title()
        rest = match.group("rest").strip()
        score_match = re.search(r"(\d+(?:\.\d+)?)", rest)
        max_score = float(score_match.group(1)) if score_match else 5.0
        description = rest if rest else None
        criteria.append(
            {
                "name": name,
                "description": description,
                "max_score": max_score,
            }
        )

    if not criteria:
        criteria = [
            {"name": "Empathy", "description": "Demonstrates empathy and rapport", "max_score": 5.0},
            {"name": "Clinical Reasoning", "description": "Identifies issues and proposes plan", "max_score": 5.0},
            {"name": "Education", "description": "Explains diagnoses and next steps", "max_score": 5.0},
        ]

    max_total = sum(c["max_score"] for c in criteria)
    return {
        "title": title_text,
        "summary": cleaned[:400],
        "criteria": criteria,
        "max_total": max_total,
    }
