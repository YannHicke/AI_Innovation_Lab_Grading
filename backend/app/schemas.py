from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CriterionScoreBase(BaseModel):
    name: str
    description: Optional[str] = None
    score: float
    max_score: float
    feedback: Optional[str] = None


class CriterionScoreResponse(CriterionScoreBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class AssignmentResponse(BaseModel):
    id: int
    title: str
    cohort: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationResponse(BaseModel):
    id: int
    rubric_title: str
    rubric_summary: Optional[str]
    feedback_summary: Optional[str]
    total_score: float
    max_total_score: float
    performance_band: Optional[str]
    share_with_student: bool
    student_identifier: Optional[str] = None
    created_at: datetime
    assignment: Optional[AssignmentResponse] = None
    grader: Optional[UserResponse] = None
    criterion_scores: List[CriterionScoreResponse]

    model_config = ConfigDict(from_attributes=True)


class EvaluationListItem(BaseModel):
    id: int
    rubric_title: str
    total_score: float
    max_total_score: float
    performance_band: Optional[str]
    student_identifier: Optional[str] = None
    created_at: datetime
    assignment: Optional[AssignmentResponse] = None
    grader: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


class EvaluationCreateResponse(BaseModel):
    evaluation: EvaluationResponse
    message: str
