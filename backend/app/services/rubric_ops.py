from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Iterable, Tuple

from sqlalchemy.orm import Session

from ..models import Assignment, Rubric, RubricItem, RubricLevel, User


def parse_due_date(raw_value: str | None) -> datetime | None:
    """Parse an ISO 8601 date string into a datetime."""
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError as exc:  # pragma: no cover - validation guard
        raise ValueError("assignment_due_date must be an ISO 8601 string") from exc


def get_or_create_assignment(
    db: Session,
    *,
    title: str,
    cohort: str | None,
    description: str | None,
    due_date: datetime | None,
) -> Assignment:
    """Fetch or create an assignment record."""
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


def get_or_create_user(
    db: Session,
    *,
    email: str,
    full_name: str | None,
    role: str | None,
) -> User:
    """Fetch or create a user record."""
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


def persist_rubric(
    db: Session,
    *,
    rubric_payload: dict,
    assignment: Assignment | None,
    creator: User | None,
    pdf_filename: str | None,
    pdf_bytes: bytes | None,
) -> tuple[Rubric, list[RubricItem]]:
    """Persist a parsed rubric and return the rubric plus created items."""
    normalized_name = pdf_filename.strip() if pdf_filename else None
    source_hash = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else None

    rubric = Rubric(
        title=rubric_payload["title"],
        summary=rubric_payload.get("summary"),
        rubric_type=rubric_payload.get("rubric_type") or "analytic",
        max_total_score=rubric_payload.get("max_total_score") or 0.0,
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
