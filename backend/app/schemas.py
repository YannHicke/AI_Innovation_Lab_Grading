from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CriterionScoreBase(BaseModel):
    rubric_item_id: Optional[int] = None
    item_type: Optional[str] = None
    name: str
    description: Optional[str] = None
    score: float
    max_score: float
    feedback: Optional[str] = None
    evidence: Optional[str] = None
    justification: Optional[str] = None


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
    rubric_id: Optional[int] = None
    rubric_type: Optional[str] = None
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
    rubric: Optional["RubricResponse"] = None
    grader: Optional[UserResponse] = None
    criterion_scores: List[CriterionScoreResponse]

    model_config = ConfigDict(from_attributes=True)


class EvaluationListItem(BaseModel):
    id: int
    rubric_id: Optional[int] = None
    rubric_title: str
    total_score: float
    max_total_score: float
    performance_band: Optional[str]
    student_identifier: Optional[str] = None
    created_at: datetime
    assignment: Optional[AssignmentResponse] = None
    grader: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


class GeneratedPrompt(BaseModel):
    criterion_name: str
    prompt_text: str


class RubricParsingInfo(BaseModel):
    items_extracted: int
    rubric_title: str
    rubric_type: str
    max_total_score: float
    criteria_names: List[str]
    generated_prompts: List[GeneratedPrompt]


class EvaluationCreateResponse(BaseModel):
    evaluation: EvaluationResponse
    message: str
    parsing_info: Optional[RubricParsingInfo] = None


class RubricLevelResponse(BaseModel):
    id: int
    level_key: Optional[str] = None
    label: str
    description: Optional[str] = None
    score: Optional[float] = None
    order_index: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class RubricItemResponse(BaseModel):
    id: int
    rubric_id: int
    name: str
    description: Optional[str] = None
    item_type: str
    max_score: Optional[float] = None
    weight: Optional[float] = None
    order_index: int
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_dict")
    levels: List[RubricLevelResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RubricResponse(BaseModel):
    id: int
    title: str
    summary: Optional[str] = None
    rubric_type: str
    max_total_score: float
    source_document_name: Optional[str] = None
    source_document_sha256: Optional[str] = None
    created_at: datetime
    assignment: Optional[AssignmentResponse] = None
    created_by: Optional[UserResponse] = None
    items: List[RubricItemResponse] = Field(default_factory=list)
    levels: List[RubricLevelResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


EvaluationResponse.model_rebuild()
