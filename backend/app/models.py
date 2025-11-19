from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


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
    created_at = Column(DateTime, default=datetime.utcnow)

    criterion_scores = relationship(
        "CriterionScore",
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )


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
