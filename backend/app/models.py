from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    created_at = Column(DateTime, default=datetime.utcnow)

    criterion_scores = relationship(
        "CriterionScore",
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    assignment = relationship("Assignment", back_populates="evaluations")
    grader = relationship("User", back_populates="evaluations")


class CriterionScore(Base):
    __tablename__ = "criterion_scores"

    id = Column(Integer, primary_key=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)
    feedback = Column(Text)

    evaluation = relationship("Evaluation", back_populates="criterion_scores")
