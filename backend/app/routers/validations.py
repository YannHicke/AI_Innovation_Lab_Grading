from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import CriterionScore, Evaluation, HumanCriterionScore, HumanGrading
from ..services.rubric_parser import pdf_bytes_to_text
from ..services.llm_utils import normalize_provider, parse_llm_json, extract_message_payload
from ..config import get_settings

router = APIRouter(prefix="/api/validations", tags=["validations"])
logger = logging.getLogger(__name__)
settings = get_settings()


def parse_human_grading_from_pdf(pdf_text: str, provider: str | None = None) -> Dict[str, Any]:
    """Parse human grading scores from PDF text using LLM."""
    from openai import OpenAI
    from anthropic import Anthropic

    provider = normalize_provider(provider, settings)

    system_prompt = """You are a JSON-only API that extracts human grading scores from documents.

CRITICAL RULES:
1. Output ONLY valid JSON - no explanations, no markdown, no code blocks
2. Start your response with { and end with }
3. Do not wrap the JSON in ```json``` or any other formatting

Required JSON structure:
{
  "grader_name": "string or null",
  "total_score": number,
  "max_total_score": number,
  "criterion_scores": [
    {
      "criterion_name": "string",
      "score": number,
      "max_score": number,
      "feedback": "string or null"
    }
  ]
}"""

    user_message = f"Extract human grading scores as JSON:\n\n{pdf_text.strip()}"

    try:
        if provider == "anthropic":
            client = Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.llm_model_anthropic,
                max_tokens=settings.llm_max_output_tokens,
                temperature=0.2,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            payload = response.content[0].text
        else:  # openai
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.llm_model_openai,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.2,
                max_tokens=settings.llm_max_output_tokens,
            )
            message = response.choices[0].message
            parsed_field = getattr(message, "parsed", None)
            if isinstance(parsed_field, dict):
                return parsed_field
            payload = extract_message_payload(message)

        return parse_llm_json(payload)
    except Exception as exc:
        logger.error("Failed to parse human grading from PDF: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse human grading from PDF: {exc}"
        ) from exc


@router.post("/{evaluation_id}/upload-human-grading")
async def upload_human_grading(
    evaluation_id: int,
    human_grading_file: UploadFile = File(...),
    llm_provider: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Upload human grading PDF for comparison with AI evaluation.

    The PDF should contain human grading scores and feedback.
    LLM will extract the scores automatically.
    """
    # Verify evaluation exists
    evaluation = (
        db.query(Evaluation)
        .filter(Evaluation.id == evaluation_id)
        .first()
    )
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Read and parse PDF
    try:
        content = await human_grading_file.read()

        # Extract text from PDF
        pdf_text = pdf_bytes_to_text(content)

        # Parse human grading using LLM
        parsed_grading = parse_human_grading_from_pdf(pdf_text, provider=llm_provider)

        # Extract data from parsed result
        grader_name_from_pdf = parsed_grading.get('grader_name')
        total_score = float(parsed_grading.get('total_score', 0))
        max_total_score = float(parsed_grading.get('max_total_score', 0))
        criterion_scores = parsed_grading.get('criterion_scores', [])

    except Exception as exc:
        logger.error("Failed to parse human grading PDF: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse human grading PDF: {exc}"
        ) from exc

    if not criterion_scores:
        raise HTTPException(
            status_code=400,
            detail="No valid criterion scores found in PDF"
        )

    # Delete existing human grading for this evaluation if any
    existing = db.query(HumanGrading).filter(
        HumanGrading.evaluation_id == evaluation_id
    ).first()
    if existing:
        db.delete(existing)
        db.flush()

    # Create new human grading record
    human_grading = HumanGrading(
        evaluation_id=evaluation_id,
        total_score=total_score,
        max_total_score=max_total_score,
        grader_name=grader_name_from_pdf,
        notes=notes,
    )
    db.add(human_grading)
    db.flush()

    # Add criterion scores
    for criterion_data in criterion_scores:
        db.add(HumanCriterionScore(
            human_grading_id=human_grading.id,
            criterion_name=criterion_data.get('criterion_name', ''),
            score=float(criterion_data.get('score', 0)),
            max_score=float(criterion_data.get('max_score', 0)),
            feedback=criterion_data.get('feedback'),
        ))

    db.commit()
    db.refresh(human_grading)

    return {
        "message": "Human grading uploaded successfully",
        "human_grading": human_grading,
        "parsed_data": {
            "grader_name": grader_name_from_pdf,
            "total_score": total_score,
            "max_total_score": max_total_score,
            "criterion_count": len(criterion_scores),
        }
    }


@router.get("/{evaluation_id}/comparison")
def get_comparison(evaluation_id: int, db: Session = Depends(get_db)):
    """Get comparison between AI and human grading for an evaluation."""
    # Get AI evaluation
    ai_evaluation = (
        db.query(Evaluation)
        .options(joinedload(Evaluation.criterion_scores))
        .filter(Evaluation.id == evaluation_id)
        .first()
    )
    if not ai_evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Get human grading
    human_grading = (
        db.query(HumanGrading)
        .options(joinedload(HumanGrading.criterion_scores))
        .filter(HumanGrading.evaluation_id == evaluation_id)
        .first()
    )
    if not human_grading:
        raise HTTPException(
            status_code=404,
            detail="No human grading found for this evaluation"
        )

    # Build comparison data
    ai_total = ai_evaluation.total_score
    human_total = human_grading.total_score
    total_difference = ai_total - human_total

    # Match criteria by name
    ai_scores_by_name = {
        cs.name: cs for cs in ai_evaluation.criterion_scores
    }
    human_scores_by_name = {
        cs.criterion_name: cs for cs in human_grading.criterion_scores
    }

    criterion_comparisons = []
    for criterion_name in set(ai_scores_by_name.keys()) | set(human_scores_by_name.keys()):
        ai_score_obj = ai_scores_by_name.get(criterion_name)
        human_score_obj = human_scores_by_name.get(criterion_name)

        comparison = {
            "criterion_name": criterion_name,
            "ai_score": ai_score_obj.score if ai_score_obj else None,
            "human_score": human_score_obj.score if human_score_obj else None,
            "ai_max_score": ai_score_obj.max_score if ai_score_obj else None,
            "human_max_score": human_score_obj.max_score if human_score_obj else None,
            "difference": None,
            "ai_feedback": ai_score_obj.feedback if ai_score_obj else None,
            "human_feedback": human_score_obj.feedback if human_score_obj else None,
        }

        if ai_score_obj and human_score_obj:
            comparison["difference"] = ai_score_obj.score - human_score_obj.score

        criterion_comparisons.append(comparison)

    # Calculate statistics
    differences = [c["difference"] for c in criterion_comparisons if c["difference"] is not None]
    mean_difference = sum(differences) / len(differences) if differences else 0
    abs_differences = [abs(d) for d in differences]
    mean_absolute_difference = sum(abs_differences) / len(abs_differences) if abs_differences else 0

    return {
        "evaluation_id": evaluation_id,
        "rubric_title": ai_evaluation.rubric_title,
        "ai_total_score": ai_total,
        "human_total_score": human_total,
        "ai_max_total_score": ai_evaluation.max_total_score,
        "human_max_total_score": human_grading.max_total_score,
        "total_difference": total_difference,
        "mean_difference": mean_difference,
        "mean_absolute_difference": mean_absolute_difference,
        "grader_name": human_grading.grader_name,
        "grader_notes": human_grading.notes,
        "criterion_comparisons": criterion_comparisons,
        "created_at": ai_evaluation.created_at.isoformat(),
    }


@router.get("")
def list_comparisons(db: Session = Depends(get_db)):
    """List all evaluations that have human grading comparisons."""
    human_gradings = (
        db.query(HumanGrading)
        .options(joinedload(HumanGrading.evaluation))
        .order_by(HumanGrading.created_at.desc())
        .all()
    )

    comparisons = []
    for hg in human_gradings:
        eval_obj = hg.evaluation
        comparisons.append({
            "evaluation_id": eval_obj.id,
            "rubric_title": eval_obj.rubric_title,
            "ai_total_score": eval_obj.total_score,
            "human_total_score": hg.total_score,
            "difference": eval_obj.total_score - hg.total_score,
            "grader_name": hg.grader_name,
            "created_at": hg.created_at.isoformat(),
        })

    return comparisons


@router.delete("/{evaluation_id}/human-grading")
def delete_human_grading(evaluation_id: int, db: Session = Depends(get_db)):
    """Delete human grading data for an evaluation."""
    human_grading = (
        db.query(HumanGrading)
        .filter(HumanGrading.evaluation_id == evaluation_id)
        .first()
    )

    if not human_grading:
        raise HTTPException(
            status_code=404,
            detail="No human grading found for this evaluation"
        )

    db.delete(human_grading)
    db.commit()

    return {"message": "Human grading deleted successfully"}
