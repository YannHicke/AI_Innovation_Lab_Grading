from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Sequence

STOP_WORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "will",
    "have",
    "your",
    "about",
    "into",
    "their",
    "they",
    "them",
    "what",
    "when",
    "were",
    "should",
    "could",
    "would",
    "while",
    "which",
    "there",
}

POSITIVE_LANGUAGE = {
    "appreciate",
    "empathize",
    "understand",
    "support",
    "encourage",
    "clarify",
    "thank",
    "together",
    "plan",
    "listen",
    "collaborate",
    "reassure",
}

NEGATIVE_LANGUAGE = {
    "angry",
    "upset",
    "frustrated",
    "confused",
    "worried",
    "concerned",
    "anxious",
}


CATEGORY_KEYWORD_HINTS = {
    "empathy": [
        "empathy",
        "rapport",
        "sorry",
        "understand",
        "appreciate",
        "concern",
        "listen",
        "acknowledge",
        "validate",
    ],
    "rapport": [
        "connect",
        "trust",
        "relationship",
        "safe",
    ],
    "reason": [
        "assessment",
        "diagnosis",
        "differential",
        "rationale",
        "plan",
        "strategy",
        "treatment",
    ],
    "plan": [
        "plan",
        "steps",
        "next",
        "follow-up",
        "monitor",
    ],
    "education": [
        "teach",
        "explain",
        "break down",
        "clarify",
        "summarize",
        "handout",
        "resources",
    ],
    "communication": [
        "discuss",
        "conversation",
        "shared",
        "collaborate",
        "together",
    ],
    "summary": [
        "summarize",
        "recap",
        "highlight",
        "key points",
    ],
}


@dataclass
class RubricCriterion:
    name: str
    description: str | None
    max_score: float
    keywords: List[str]


@dataclass
class CriterionEvaluation:
    name: str
    description: str | None
    score: float
    max_score: float
    evidence: str
    justification: str

    @property
    def normalized(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0


class TranscriptInsights:
    def __init__(self, text: str) -> None:
        normalized = text.replace("\r", " ").strip()
        self.sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
        lowered = normalized.lower()
        self.tokens = re.findall(r"[a-z']+", lowered)
        self.token_counts = Counter(self.tokens)
        self.total_words = max(len(self.tokens), 1)

    def sentences_with_keywords(self, keywords: Iterable[str]) -> List[str]:
        words = {kw.lower() for kw in keywords if kw}
        if not words or not self.sentences:
            return []
        matched: List[str] = []
        for sentence in self.sentences:
            lowered = sentence.lower()
            if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):
                matched.append(sentence)
        return matched

    def language_hits(self, lexicon: Iterable[str]) -> int:
        return sum(self.token_counts.get(word.lower(), 0) for word in lexicon)

    def language_ratio(self, lexicon: Iterable[str]) -> float:
        hits = self.language_hits(lexicon)
        if not hits:
            return 0.0
        return min(0.3, hits / self.total_words * 6)


def score_criteria(criteria: List[dict], transcript_text: str) -> dict:
    rubric = _breakdown_rubric(criteria)
    insights = TranscriptInsights(transcript_text)
    evaluations = [_score_single_criterion(item, insights) for item in rubric]
    aggregate = _aggregate_feedback(evaluations)

    return {
        "criterion_scores": [
            {
                "name": item.name,
                "description": item.description,
                "score": item.score,
                "max_score": item.max_score,
                "feedback": item.justification,
                "evidence": item.evidence,
                "justification": item.justification,
            }
            for item in evaluations
        ],
        "total_score": aggregate["total_score"],
        "max_total_score": aggregate["max_total_score"],
        "performance_band": aggregate["performance_band"],
        "performance_level": aggregate["performance_level"],
        "summary": aggregate["summary"],
        "key_strengths": aggregate["key_strengths"],
        "areas_for_development": aggregate["areas_for_development"],
        "narrative_feedback": aggregate["narrative_feedback"],
    }


def _breakdown_rubric(criteria: List[dict]) -> List[RubricCriterion]:
    rubric: List[RubricCriterion] = []
    for item in criteria:
        name = item.get("name", "Criterion").strip() or "Criterion"
        description = item.get("description")
        max_score = float(item.get("max_score", 5.0))
        keywords = _extract_keywords(name, description)
        rubric.append(RubricCriterion(name=name, description=description, max_score=max_score, keywords=keywords))
    return rubric


def _extract_keywords(name: str, description: str | None) -> List[str]:
    base = f"{name} {description or ''}".lower()

    def _add_keywords(container: list[str], words: Iterable[str]) -> None:
        for word in words:
            tokens = re.findall(r"[a-z']+", word.lower())
            for token in tokens:
                if len(token) <= 3 or token in STOP_WORDS:
                    continue
                if token not in container:
                    container.append(token)

    ordered: list[str] = []
    primary_tokens = re.findall(r"[a-z']+", base)
    _add_keywords(ordered, primary_tokens)

    for hint, extras in CATEGORY_KEYWORD_HINTS.items():
        if hint in base:
            _add_keywords(ordered, extras)

    if not ordered:
        _add_keywords(ordered, name.split())
    if not ordered:
        ordered.append("communication")

    return ordered[:12]


def _score_single_criterion(criterion: RubricCriterion, insights: TranscriptInsights) -> CriterionEvaluation:
    keywords = criterion.keywords
    keyword_hits = sum(insights.token_counts.get(word, 0) for word in keywords)
    unique_hits = sum(1 for word in keywords if insights.token_counts.get(word, 0))
    effective_pool = max(4, min(len(keywords), 8))
    coverage = min(1.0, unique_hits / effective_pool)
    density = min(1.0, keyword_hits / (effective_pool * 1.5))
    signal = min(1.0, 0.7 * coverage + 0.3 * density)

    evidence_sentences = insights.sentences_with_keywords(keywords)
    coherence_bonus = min(0.28, len(evidence_sentences) * 0.07)
    positive_ratio = insights.language_ratio(POSITIVE_LANGUAGE)
    negative_ratio = insights.language_ratio(NEGATIVE_LANGUAGE)

    score_ratio = max(0.15, min(1.0, signal + coherence_bonus + (positive_ratio * 1.2) - (negative_ratio * 0.7)))
    score_value = round(score_ratio * criterion.max_score, 2)

    evidence = " / ".join(evidence_sentences[:2])
    if not evidence:
        evidence = "No direct sentence-level evidence captured; consider adding explicit statements."

    justification = _build_justification(coverage, len(evidence_sentences), positive_ratio, negative_ratio)

    return CriterionEvaluation(
        name=criterion.name,
        description=criterion.description,
        score=score_value,
        max_score=criterion.max_score,
        evidence=evidence,
        justification=justification,
    )


def _build_justification(coverage: float, evidence_count: int, positive_ratio: float, negative_ratio: float) -> str:
    coverage_pct = int(coverage * 100)
    tone: str
    if negative_ratio > 0.18:
        tone = "Tone occasionally undermined clarity."
    elif positive_ratio > 0.12:
        tone = "Tone reinforced rapport throughout."
    else:
        tone = "Tone remained neutral."
    evidence_text = f"{evidence_count} supporting sentence(s) located." if evidence_count else "No sentence-level matches found."
    return f"{coverage_pct}% rubric alignment detected. {evidence_text} {tone}"


def _aggregate_feedback(evaluations: Sequence[CriterionEvaluation]) -> dict:
    total_score = round(sum(item.score for item in evaluations), 2)
    max_total = round(sum(item.max_score for item in evaluations), 2)
    percent = (total_score / max_total) * 100 if max_total else 0.0
    band = performance_band(percent)

    key_strengths = [
        f"{item.name}: {item.score}/{item.max_score}"
        for item in sorted(evaluations, key=lambda c: c.normalized, reverse=True)
        if item.normalized >= 0.7
    ][:3]

    areas_for_development = [
        f"{item.name}: {item.score}/{item.max_score}"
        for item in sorted(evaluations, key=lambda c: c.normalized)
        if item.normalized <= 0.5
    ][:3]

    summary_parts = [f"Overall performance is {percent:.1f}% ({band})."]
    if key_strengths:
        summary_parts.append(f"Standout area: {key_strengths[0]}.")
    if areas_for_development:
        summary_parts.append(f"Priority focus: {areas_for_development[0]}.")
    summary = " ".join(summary_parts)

    narrative = _build_narrative(band, total_score, max_total, key_strengths, areas_for_development)

    return {
        "total_score": total_score,
        "max_total_score": max_total,
        "performance_band": band,
        "performance_level": band,
        "key_strengths": key_strengths,
        "areas_for_development": areas_for_development,
        "summary": summary,
        "narrative_feedback": narrative,
    }


def _build_narrative(
    band: str,
    total_score: float,
    max_total: float,
    strengths: List[str],
    gaps: List[str],
) -> str:
    parts = [f"{band} overall ({total_score}/{max_total})."]
    if strengths:
        parts.append(f"Strengths centered around {strengths[0].split(':', 1)[0]}.")
    if gaps:
        parts.append(f"Growth opportunity in {gaps[0].split(':', 1)[0]}.")
    if len(gaps) > 1:
        parts.append("Secondary focus on balance and clarity across other criteria.")
    return " ".join(parts)


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
