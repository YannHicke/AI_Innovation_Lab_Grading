from __future__ import annotations

from datetime import datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .database import Base, engine, get_db
from .models import Assignment, CriterionScore, Evaluation, User
from .schemas import EvaluationCreateResponse, EvaluationListItem, EvaluationResponse
from .services.rubric_parser import parse_rubric, pdf_bytes_to_text
from .services.scoring import score_criteria

settings = get_settings()
Base.metadata.create_all(bind=engine)

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

    rubric = parse_rubric(pdf_text)
    scoring = score_criteria(rubric["criteria"], transcript_text)

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

    evaluation = Evaluation(
        transcript_text=transcript_text,
        rubric_title=rubric["title"],
        rubric_summary=rubric["summary"],
        feedback_summary=scoring["summary"],
        total_score=scoring["total_score"],
        max_total_score=scoring["max_total_score"],
        performance_band=scoring["performance_band"],
        share_with_student=share_with_student,
        student_identifier=normalized_student_identifier,
        assignment=assignment,
        grader=grader,
    )
    db.add(evaluation)
    db.flush()

    for item in scoring["criterion_scores"]:
        db.add(
            CriterionScore(
                evaluation_id=evaluation.id,
                name=item["name"],
                description=item.get("description"),
                score=item["score"],
                max_score=item["max_score"],
                feedback=item.get("feedback"),
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
        )
        .order_by(Evaluation.created_at.desc())
        .limit(min(limit, 50))
    )
    return list(query)


@app.get("/api/evaluations/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    evaluation = (
        db.query(Evaluation)
        .options(
            joinedload(Evaluation.assignment),
            joinedload(Evaluation.grader),
            joinedload(Evaluation.criterion_scores),
        )
        .filter(Evaluation.id == evaluation_id)
        .first()
    )
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation
