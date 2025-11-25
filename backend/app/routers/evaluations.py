from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
from ..services.scoring import ScoringError, score_criteria

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
        scoring = score_criteria(
            scoring_input,
            transcript_text,
            rubric_type=rubric.rubric_type,
            provider=llm_provider,
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
        scoring = score_criteria(
            scoring_input,
            transcript_text,
            rubric_type=rubric_record.rubric_type,
            provider=llm_provider,
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
