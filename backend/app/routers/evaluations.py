from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..database import get_db
from ..models import Assignment, CriterionScore, Evaluation, Rubric, RubricItem, User
from ..schemas import EvaluationCreateResponse, EvaluationListItem, EvaluationResponse
from ..services.rubric_manager import build_parsing_info, scoring_payload_from_models, scoring_payload_from_payload
from ..services.rubric_ops import (
    get_or_create_assignment,
    get_or_create_user,
    parse_due_date,
    persist_rubric,
)
from ..services.rubric_parser import RubricParsingError, parse_rubric, pdf_bytes_to_text
from ..services.scoring import ScoringError, score_criteria, score_criteria_parallel
from ..services.pdf_generator import generate_evaluation_pdf

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/with-rubric")
async def create_evaluation_with_saved_rubric(
    transcript_text: str = Form(...),
    rubric_id: int = Form(...),
    share_with_student: bool = Form(False),
    student_identifier: str | None = Form(None),
    grader_email: str | None = Form(None),
    grader_name: str | None = Form(None),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Create an evaluation using a pre-saved rubric."""
    if not transcript_text.strip():
        raise HTTPException(status_code=400, detail="Transcript text is required.")

    rubric = (
        db.query(Rubric)
        .options(joinedload(Rubric.items))
        .filter(Rubric.id == rubric_id)
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")
    if not rubric.items:
        raise HTTPException(status_code=400, detail="Rubric has no criteria")

    grader = None
    normalized_email = grader_email.strip() if grader_email else None
    if normalized_email:
        grader = get_or_create_user(
            db,
            email=normalized_email,
            full_name=grader_name.strip() if grader_name else None,
            role="faculty",
        )

    fallback_max = (rubric.max_total_score or 0.0) / max(len(rubric.items), 1)
    scoring_input = scoring_payload_from_models(rubric.items, fallback_max)

    try:
        # Use parallel scoring for better performance
        scoring = await score_criteria_parallel(
            scoring_input,
            transcript_text,
            rubric_type=rubric.rubric_type,
            provider=llm_provider,
            batch_size=10,  # Process 10 items concurrently
        )
    except ScoringError as exc:
        raise HTTPException(status_code=503, detail=f"Scoring failed: {exc}") from exc

    evaluation = Evaluation(
        transcript_text=transcript_text,
        rubric_title=rubric.title,
        rubric_summary=rubric.summary,
        feedback_summary=scoring["summary"],
        total_score=scoring["total_score"],
        max_total_score=scoring["max_total_score"],
        performance_band=scoring["performance_band"],
        share_with_student=share_with_student,
        student_identifier=student_identifier.strip() if student_identifier else None,
        grader=grader,
        rubric=rubric,
    )
    db.add(evaluation)
    db.flush()

    for item in scoring["criterion_scores"]:
        db.add(
            CriterionScore(
                evaluation_id=evaluation.id,
                rubric_item_id=item.get("rubric_item_id"),
                name=item["name"],
                description=item.get("description"),
                score=item["score"],
                max_score=item["max_score"],
                feedback=item.get("feedback"),
                evidence=item.get("evidence"),
                justification=item.get("justification"),
            )
        )

    db.commit()
    db.refresh(evaluation)

    return {"evaluation": evaluation, "message": "Evaluation created successfully"}


@router.post("", response_model=EvaluationCreateResponse)
async def create_evaluation(
    transcript_text: str = Form(...),
    rubric_pdf: UploadFile = File(...),
    share_with_student: bool = Form(settings.share_results_default),
    student_identifier: str | None = Form(None),
    assignment_name: str | None = Form(None),
    assignment_cohort: str | None = Form(None),
    assignment_description: str | None = Form(None),
    assignment_due_date: str | None = Form(None),
    grader_email: str | None = Form(None),
    grader_name: str | None = Form(None),
    grader_role: str | None = Form(None),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not transcript_text.strip():
        raise HTTPException(status_code=400, detail="Transcript text is required.")

    pdf_data = await rubric_pdf.read()
    if not pdf_data:
        raise HTTPException(status_code=400, detail="Rubric PDF is empty.")

    try:
        pdf_text = pdf_bytes_to_text(pdf_data)
    except Exception as exc:  # pragma: no cover - defensive catch
        raise HTTPException(status_code=422, detail=f"Unable to read PDF: {exc}") from exc

    assignment = None
    normalized_assignment_name = assignment_name.strip() if assignment_name else None
    if normalized_assignment_name:
        try:
            due_date = parse_due_date(assignment_due_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        assignment = get_or_create_assignment(
            db,
            title=normalized_assignment_name,
            cohort=assignment_cohort.strip() if assignment_cohort else None,
            description=assignment_description.strip() if assignment_description else None,
            due_date=due_date,
        )

    grader = None
    normalized_email = grader_email.strip() if grader_email else None
    if normalized_email:
        grader = get_or_create_user(
            db,
            email=normalized_email,
            full_name=grader_name.strip() if grader_name else None,
            role=(grader_role.strip() if grader_role else None) or "faculty",
        )

    normalized_student_identifier = student_identifier.strip() if student_identifier else None

    try:
        logger.info("PDF parsing started for file=%s", rubric_pdf.filename)
        rubric_payload = parse_rubric(pdf_text, provider=llm_provider)
        logger.info(
            "PDF parsing completed; extracted %d criteria",
            len(rubric_payload.get("criteria") or []),
        )
    except RubricParsingError as exc:
        raise HTTPException(status_code=503, detail=f"Rubric parsing failed: {exc}") from exc

    rubric_record, rubric_items = persist_rubric(
        db,
        rubric_payload=rubric_payload,
        assignment=assignment,
        creator=grader,
        pdf_filename=rubric_pdf.filename,
        pdf_bytes=pdf_data,
    )

    fallback_max = (rubric_record.max_total_score or rubric_payload.get("max_total_score") or 0.0) / max(len(rubric_items), 1)
    scoring_input = scoring_payload_from_models(rubric_items, fallback_max)

    try:
        # Use parallel scoring for better performance
        scoring = await score_criteria_parallel(
            scoring_input,
            transcript_text,
            rubric_type=rubric_record.rubric_type,
            provider=llm_provider,
            batch_size=10,  # Process 10 items concurrently
        )
    except ScoringError as exc:
        raise HTTPException(status_code=503, detail=f"Scoring failed: {exc}") from exc

    evaluation = Evaluation(
        transcript_text=transcript_text,
        rubric_title=rubric_payload["title"],
        rubric_summary=rubric_payload["summary"],
        feedback_summary=scoring["summary"],
        total_score=scoring["total_score"],
        max_total_score=scoring["max_total_score"],
        performance_band=scoring["performance_band"],
        share_with_student=share_with_student,
        student_identifier=normalized_student_identifier,
        assignment=assignment,
        grader=grader,
        rubric=rubric_record,
    )
    db.add(evaluation)
    db.flush()

    for item in scoring["criterion_scores"]:
        db.add(
            CriterionScore(
                evaluation_id=evaluation.id,
                rubric_item_id=item.get("rubric_item_id"),
                name=item["name"],
                description=item.get("description"),
                score=item["score"],
                max_score=item["max_score"],
                feedback=item.get("feedback"),
                evidence=item.get("evidence"),
                justification=item.get("justification"),
            )
        )

    db.commit()
    db.refresh(evaluation)

    parsing_info = build_parsing_info(
        rubric_title=rubric_payload["title"],
        rubric_type=rubric_record.rubric_type,
        max_total_score=rubric_record.max_total_score,
        scoring_items=scoring_input,
    )

    return EvaluationCreateResponse(
        evaluation=evaluation,
        message="Evaluation recorded.",
        parsing_info=parsing_info,
    )


@router.get("", response_model=list[EvaluationListItem])
def list_evaluations(limit: int = 10, db: Session = Depends(get_db)):
    query = (
        db.query(Evaluation)
        .options(
            joinedload(Evaluation.assignment),
            joinedload(Evaluation.grader),
            joinedload(Evaluation.rubric),
        )
        .order_by(Evaluation.created_at.desc())
        .limit(min(limit, 50))
    )
    return list(query)


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    rubric_loader = joinedload(Evaluation.rubric)
    rubric_loader.joinedload(Rubric.items).joinedload(RubricItem.levels)
    rubric_loader.joinedload(Rubric.levels)
    evaluation = (
        db.query(Evaluation)
        .options(
            joinedload(Evaluation.assignment),
            joinedload(Evaluation.grader),
            joinedload(Evaluation.criterion_scores),
            rubric_loader,
        )
        .filter(Evaluation.id == evaluation_id)
        .first()
    )
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


@router.put("/{evaluation_id}")
def update_evaluation(
    evaluation_id: int,
    update_data: dict,
    db: Session = Depends(get_db),
):
    """Update an evaluation's scores and title."""
    evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    try:
        # Update rubric title
        if 'rubric_title' in update_data:
            evaluation.rubric_title = update_data['rubric_title']

        # Update total score
        if 'total_score' in update_data:
            evaluation.total_score = update_data['total_score']

        # Update criterion scores
        if 'criterion_scores' in update_data:
            for score_update in update_data['criterion_scores']:
                criterion_score = (
                    db.query(CriterionScore)
                    .filter(CriterionScore.id == score_update['id'])
                    .first()
                )
                if criterion_score:
                    criterion_score.score = score_update['score']
                    if 'feedback' in score_update:
                        criterion_score.feedback = score_update['feedback']

        db.commit()
        db.refresh(evaluation)

        return {"message": "Evaluation updated successfully", "evaluation": evaluation}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update evaluation: {exc}") from exc


@router.post("/{evaluation_id}/learner-report")
async def generate_learner_report(
    evaluation_id: int,
    request_data: dict,
    db: Session = Depends(get_db),
):
    """Generate a student learner report with strengths, growth opportunities, and actionable suggestions."""
    # Fetch evaluation with all related data
    evaluation = (
        db.query(Evaluation)
        .options(
            joinedload(Evaluation.criterion_scores),
        )
        .filter(Evaluation.id == evaluation_id)
        .first()
    )

    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    llm_provider = request_data.get('llm_provider', 'anthropic')

    # Build prompt for learner report generation
    criterion_details = "\n".join([
        f"- {cs.name}: {cs.score}/{cs.max_score} - {cs.feedback}"
        for cs in evaluation.criterion_scores
    ])

    system_prompt = """You are an educational feedback specialist. Generate a comprehensive student learner report based on the evaluation results.

Your response must be valid JSON with this exact structure:
{
  "top_strengths": ["strength 1", "strength 2", "strength 3"],
  "growth_opportunities": ["opportunity 1", "opportunity 2", "opportunity 3"],
  "actionable_suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"]
}

Guidelines:
- Top Strengths: Identify 3 specific areas where the student excelled
- Growth Opportunities: Identify 3 areas where improvement would be beneficial (phrase positively)
- Actionable Suggestions: Provide 3 concrete, specific actions the student can take to improve

Be encouraging, specific, and constructive."""

    user_prompt = f"""Generate a learner report for this evaluation:

Rubric: {evaluation.rubric_title}
Performance Band: {evaluation.performance_band}
Total Score: {evaluation.total_score}/{evaluation.max_total_score}
Overall Feedback: {evaluation.feedback_summary}

Criterion Scores:
{criterion_details}

Transcript Text:
{evaluation.transcript_text[:2000]}

Generate the learner report as JSON."""

    try:
        from ..services.llm_utils import call_llm

        response_text = await call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=llm_provider,
            temperature=0.7,
        )

        # Parse JSON response
        import json
        learner_report = json.loads(response_text)

        # Validate structure
        if not all(key in learner_report for key in ['top_strengths', 'growth_opportunities', 'actionable_suggestions']):
            raise ValueError("Invalid learner report structure")

        return learner_report

    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse learner report JSON: {exc}")
        raise HTTPException(status_code=503, detail="Failed to generate learner report - invalid JSON response") from exc
    except Exception as exc:
        logger.error(f"Error generating learner report: {exc}")
        raise HTTPException(status_code=503, detail=f"Failed to generate learner report: {exc}") from exc


@router.get("/{evaluation_id}/pdf")
def download_evaluation_pdf(evaluation_id: int, db: Session = Depends(get_db)):
    """Generate and download a PDF report for an evaluation."""
    # Fetch evaluation with all related data
    evaluation = (
        db.query(Evaluation)
        .options(
            joinedload(Evaluation.criterion_scores),
        )
        .filter(Evaluation.id == evaluation_id)
        .first()
    )

    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Convert evaluation to dict for PDF generation
    evaluation_dict = {
        "id": evaluation.id,
        "rubric_title": evaluation.rubric_title,
        "created_at": evaluation.created_at.isoformat(),
        "performance_band": evaluation.performance_band,
        "total_score": evaluation.total_score,
        "max_total_score": evaluation.max_total_score,
        "feedback_summary": evaluation.feedback_summary,
        "key_strengths": evaluation.key_strengths or [],
        "areas_for_development": evaluation.areas_for_development or [],
        "criterion_scores": [
            {
                "id": cs.id,
                "name": cs.name,
                "description": cs.description,
                "score": cs.score,
                "max_score": cs.max_score,
                "feedback": cs.feedback,
            }
            for cs in evaluation.criterion_scores
        ],
    }

    # Generate PDF
    pdf_buffer = generate_evaluation_pdf(evaluation_dict)

    # Create filename
    safe_title = "".join(c for c in evaluation.rubric_title if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"evaluation_{evaluation_id}_{safe_title[:30]}.pdf"

    # Return as downloadable file
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
