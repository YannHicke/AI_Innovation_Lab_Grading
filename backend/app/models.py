from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255))
    role = Column(String(50), default="faculty")
    created_at = Column(DateTime, default=datetime.utcnow)

    evaluations = relationship("Evaluation", back_populates="grader")
    created_rubrics = relationship("Rubric", back_populates="created_by")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("title", "cohort", name="uq_assignments_title_cohort"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    cohort = Column(String(100))
    description = Column(Text)
    due_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    evaluations = relationship("Evaluation", back_populates="assignment")
    rubrics = relationship("Rubric", back_populates="assignment")


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text)
    rubric_type = Column(String(50), default="analytic")
    max_total_score = Column(Float, nullable=False, default=0.0)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="SET NULL"))
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    source_document_name = Column(String(255))
    source_document_sha256 = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)

    assignment = relationship("Assignment", back_populates="rubrics")
    created_by = relationship("User", back_populates="created_rubrics")
    items = relationship("RubricItem", back_populates="rubric", cascade="all, delete-orphan")
    levels = relationship("RubricLevel", back_populates="rubric", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="rubric")


class RubricItem(Base):
    __tablename__ = "rubric_items"

    id = Column(Integer, primary_key=True, index=True)
    rubric_id = Column(Integer, ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    item_type = Column(String(50), default="criterion")
    max_score = Column(Float)
    weight = Column(Float)
    order_index = Column(Integer, default=0)
    metadata_json = Column("metadata", JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    rubric = relationship("Rubric", back_populates="items")
    levels = relationship("RubricLevel", back_populates="rubric_item", cascade="all, delete-orphan")
    criterion_scores = relationship("CriterionScore", back_populates="rubric_item")

    @property
    def metadata_dict(self) -> dict:
        return self.metadata_json or {}


class RubricLevel(Base):
    __tablename__ = "rubric_levels"

    id = Column(Integer, primary_key=True, index=True)
    rubric_id = Column(Integer, ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False)
    rubric_item_id = Column(Integer, ForeignKey("rubric_items.id", ondelete="CASCADE"))
    level_key = Column(String(50))
    label = Column(String(255))
    description = Column(Text)
    score = Column(Float)
    order_index = Column(Integer, default=0)

    rubric = relationship("Rubric", back_populates="levels")
    rubric_item = relationship("RubricItem", back_populates="levels")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    transcript_text = Column(Text, nullable=False)
    rubric_title = Column(String(255), default="Untitled Rubric")
    rubric_summary = Column(Text)
    feedback_summary = Column(Text)
    total_score = Column(Float, default=0.0)
    max_total_score = Column(Float, default=0.0)
    performance_band = Column(String(50))
    share_with_student = Column(Boolean, default=False)
    student_identifier = Column(String(255))
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="SET NULL"))
    grader_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    rubric_id = Column(Integer, ForeignKey("rubrics.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow)

    criterion_scores = relationship(
        "CriterionScore",
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    assignment = relationship("Assignment", back_populates="evaluations")
    grader = relationship("User", back_populates="evaluations")
    rubric = relationship("Rubric", back_populates="evaluations")

    @property
    def rubric_type(self) -> str | None:
        return self.rubric.rubric_type if self.rubric else None


class CriterionScore(Base):
    __tablename__ = "criterion_scores"

    id = Column(Integer, primary_key=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id", ondelete="CASCADE"))
    rubric_item_id = Column(Integer, ForeignKey("rubric_items.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)
    feedback = Column(Text)
    evidence = Column(Text)
    justification = Column(Text)

    evaluation = relationship("Evaluation", back_populates="criterion_scores")
    rubric_item = relationship("RubricItem", back_populates="criterion_scores")
