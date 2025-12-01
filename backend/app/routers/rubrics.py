from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Rubric, RubricItem
from ..schemas import RubricParsingInfo, RubricResponse, RubricSaveRequest
from ..services.rubric_manager import build_parsing_info, scoring_payload_from_payload
from ..services.rubric_parser import RubricParsingError, parse_rubric, pdf_bytes_to_text

router = APIRouter(prefix="/api/rubrics", tags=["rubrics"])


@router.post("/parse")
async def parse_rubric_only(
    llm_provider: str | None = Form(None),
    rubric_pdf: UploadFile = File(...),
):
    """Parse a rubric PDF and return the extracted information without saving."""
    pdf_data = await rubric_pdf.read()
    if not pdf_data:
        raise HTTPException(status_code=400, detail="Rubric PDF is empty.")

    try:
        pdf_text = pdf_bytes_to_text(pdf_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Unable to read PDF: {exc}") from exc

    try:
        rubric_payload = parse_rubric(pdf_text, provider=llm_provider)
    except RubricParsingError as exc:
        raise HTTPException(status_code=503, detail=f"Rubric parsing failed: {exc}") from exc

    scoring_preview = scoring_payload_from_payload(rubric_payload.get("criteria", []))
    parsing_info = build_parsing_info(
        rubric_title=rubric_payload["title"],
        rubric_type=rubric_payload.get("rubric_type") or "analytic",
        max_total_score=rubric_payload.get("max_total_score") or 0.0,
        scoring_items=scoring_preview,
    )

    return {"rubric": rubric_payload, "parsing_info": parsing_info.model_dump()}


@router.post("")
def save_rubric(
    rubric_data: RubricSaveRequest,
    db: Session = Depends(get_db),
):
    """Save a modified rubric to the database."""
    try:
        rubric = Rubric(
            title=rubric_data.title or "Untitled Rubric",
            summary=rubric_data.summary or "",
            rubric_type=rubric_data.rubric_type or "analytic",
            max_total_score=rubric_data.max_total_score or 0.0,
        )
        db.add(rubric)
        db.flush()

        for order, criterion in enumerate(rubric_data.criteria):
            item = RubricItem(
                rubric_id=rubric.id,
                name=criterion.name or f"Criterion {order + 1}",
                description=criterion.description,
                item_type=(criterion.item_type or "criterion").strip().lower(),
                max_score=criterion.max_score,
                weight=criterion.weight,
                order_index=order,
                metadata_json=criterion.metadata or {},
            )
            db.add(item)

        db.commit()
        db.refresh(rubric)

        return {"id": rubric.id, "message": "Rubric saved successfully"}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save rubric: {exc}") from exc


@router.put("/{rubric_id}")
def update_rubric(
    rubric_id: int,
    rubric_data: RubricSaveRequest,
    db: Session = Depends(get_db),
):
    """Update an existing rubric and replace its criteria."""
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    try:
        rubric.title = rubric_data.title or "Untitled Rubric"
        rubric.summary = rubric_data.summary or ""
        rubric.rubric_type = rubric_data.rubric_type or "analytic"
        rubric.max_total_score = rubric_data.max_total_score or 0.0

        for level in list(rubric.levels):
            db.delete(level)
        for item in list(rubric.items):
            db.delete(item)
        db.flush()

        for order, criterion in enumerate(rubric_data.criteria):
            db.add(
                RubricItem(
                    rubric_id=rubric.id,
                    name=criterion.name or f"Criterion {order + 1}",
                    description=criterion.description,
                    item_type=(criterion.item_type or "criterion").strip().lower(),
                    max_score=criterion.max_score,
                    weight=criterion.weight,
                    order_index=order,
                    metadata_json=criterion.metadata or {},
                )
            )

        db.commit()
        db.refresh(rubric)
        return {"id": rubric.id, "message": "Rubric updated successfully"}
    except Exception as exc:  # pragma: no cover - defensive rollback
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update rubric: {exc}") from exc


@router.get("", response_model=list[dict])
def list_rubrics(db: Session = Depends(get_db)):
    """List all saved rubrics."""
    rubrics = db.query(Rubric).order_by(Rubric.created_at.desc()).all()
    return [
        {
            "id": rubric.id,
            "title": rubric.title,
            "rubric_type": rubric.rubric_type,
            "max_total_score": rubric.max_total_score,
            "items_count": len(rubric.items),
            "created_at": rubric.created_at.isoformat(),
        }
        for rubric in rubrics
    ]


@router.get("/{rubric_id}", response_model=RubricResponse)
def get_rubric(rubric_id: int, db: Session = Depends(get_db)):
    """Load a single rubric with all related data."""
    rubric = (
        db.query(Rubric)
        .options(
            joinedload(Rubric.assignment),
            joinedload(Rubric.created_by),
            joinedload(Rubric.items).joinedload(RubricItem.levels),
            joinedload(Rubric.levels),
        )
        .filter(Rubric.id == rubric_id)
        .first()
    )
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")
    return rubric


@router.delete("/{rubric_id}")
def delete_rubric(rubric_id: int, db: Session = Depends(get_db)):
    """Delete a saved rubric."""
    rubric = db.query(Rubric).filter(Rubric.id == rubric_id).first()
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    db.delete(rubric)
    db.commit()
    return {"message": "Rubric deleted successfully"}
