from __future__ import annotations

from datetime import datetime
import hashlib
import logging

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .database import Base, engine, ensure_schema, get_db
from .models import Assignment, CriterionScore, Evaluation, Rubric, RubricItem, RubricLevel, User
from .schemas import EvaluationCreateResponse, EvaluationListItem, EvaluationResponse
from .services.rubric_parser import RubricParsingError, parse_rubric, pdf_bytes_to_text
from .services.scoring import ScoringError, score_criteria

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="AI Innovation Lab Grading API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


def _parse_due_date(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=422, detail="assignment_due_date must be an ISO 8601 string") from exc


def _get_or_create_assignment(
    db: Session,
    *,
    title: str,
    cohort: str | None,
    description: str | None,
    due_date: datetime | None,
) -> Assignment:
    query = db.query(Assignment).filter(Assignment.title == title)
    if cohort:
        query = query.filter(Assignment.cohort == cohort)
    assignment = query.first()
    if assignment:
        updated = False
        if description and assignment.description != description:
            assignment.description = description
            updated = True
        if due_date and assignment.due_date != due_date:
            assignment.due_date = due_date
            updated = True
        if updated:
            db.flush()
        return assignment

    assignment = Assignment(title=title, cohort=cohort, description=description, due_date=due_date)
    db.add(assignment)
    db.flush()
    return assignment


def _get_or_create_user(
    db: Session,
    *,
    email: str,
    full_name: str | None,
    role: str | None,
) -> User:
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if user:
        updated = False
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if role and user.role != role:
            user.role = role
            updated = True
        if updated:
            db.flush()
        return user

    user = User(email=normalized_email, full_name=full_name, role=role or "faculty")
    db.add(user)
    db.flush()
    return user


def _persist_rubric(
    db: Session,
    *,
    rubric_payload: dict,
    assignment: Assignment | None,
    creator: User | None,
    pdf_filename: str | None,
    pdf_bytes: bytes | None,
) -> tuple[Rubric, list[RubricItem]]:
    normalized_name = pdf_filename.strip() if pdf_filename else None
    source_hash = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else None

    rubric = Rubric(
        title=rubric_payload["title"],
        summary=rubric_payload.get("summary"),
        rubric_type=rubric_payload.get("rubric_type") or "analytic",
        max_total_score=rubric_payload.get("max_total") or 0.0,
        assignment=assignment,
        created_by=creator,
        source_document_name=normalized_name,
        source_document_sha256=source_hash,
    )
    db.add(rubric)
    db.flush()

    items: list[RubricItem] = []
    for order, criterion in enumerate(rubric_payload.get("criteria", [])):
        metadata = criterion.get("metadata") or {}
        item = RubricItem(
            rubric_id=rubric.id,
            name=criterion.get("name") or f"Criterion {order + 1}",
            description=criterion.get("description"),
            item_type=(criterion.get("item_type") or "criterion").strip().lower(),
            max_score=criterion.get("max_score"),
            weight=criterion.get("weight"),
            order_index=order,
            metadata_json=metadata,
        )
        db.add(item)
        items.append(item)
    db.flush()

    for criterion, item in zip(rubric_payload.get("criteria", []), items, strict=False):
        for level_order, level in enumerate((criterion.get("metadata") or {}).get("performance_levels") or [], start=1):
            db.add(
                RubricLevel(
                    rubric_id=rubric.id,
                    rubric_item_id=item.id,
                    level_key=level.get("level_key"),
                    label=level.get("label"),
                    description=level.get("description"),
                    score=level.get("score"),
                    order_index=level_order,
                )
            )

    for order, level in enumerate(rubric_payload.get("levels") or [], start=1):
        db.add(
            RubricLevel(
                rubric_id=rubric.id,
                rubric_item_id=None,
                level_key=level.get("level_key"),
                label=level.get("label"),
                description=level.get("description"),
                score=level.get("score"),
                order_index=order,
            )
        )

    db.flush()
    return rubric, items


@app.post("/api/evaluations", response_model=EvaluationCreateResponse)
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
        due_date = _parse_due_date(assignment_due_date)
        assignment = _get_or_create_assignment(
            db,
            title=normalized_assignment_name,
            cohort=assignment_cohort.strip() if assignment_cohort else None,
            description=assignment_description.strip() if assignment_description else None,
            due_date=due_date,
        )

    grader = None
    normalized_email = grader_email.strip() if grader_email else None
    if normalized_email:
        grader = _get_or_create_user(
            db,
            email=normalized_email,
            full_name=grader_name.strip() if grader_name else None,
            role=(grader_role.strip() if grader_role else None) or "faculty",
        )

    normalized_student_identifier = student_identifier.strip() if student_identifier else None

    try:
        logging.info("PDF parsing started for file=%s", rubric_pdf.filename)
        rubric_payload = parse_rubric(pdf_text)
        logging.info("PDF parsing completed; extracted %d criteria", len(rubric_payload.get("criteria") or []))
    except RubricParsingError as exc:
        raise HTTPException(status_code=503, detail=f"Rubric parsing failed: {exc}") from exc

    rubric_record, rubric_items = _persist_rubric(
        db,
        rubric_payload=rubric_payload,
        assignment=assignment,
        creator=grader,
        pdf_filename=rubric_pdf.filename,
        pdf_bytes=pdf_data,
    )

    scoring_input: list[dict] = []
    fallback_max = (rubric_record.max_total_score or rubric_payload.get("max_total") or 0.0) / max(len(rubric_items), 1)
    for item in rubric_items:
        scoring_input.append(
            {
                "rubric_item_id": item.id,
                "name": item.name,
                "description": item.description,
                "max_score": item.max_score or fallback_max,
                "item_type": item.item_type,
                "weight": item.weight,
                "metadata": item.metadata_dict,
            }
        )

    try:
        scoring = score_criteria(scoring_input, transcript_text, rubric_type=rubric_record.rubric_type)
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

    return EvaluationCreateResponse(evaluation=evaluation, message="Evaluation recorded.")


@app.get("/api/evaluations", response_model=list[EvaluationListItem])
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


@app.get("/api/evaluations/{evaluation_id}", response_model=EvaluationResponse)
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
