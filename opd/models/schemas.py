from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared enums (mirror DB enums for API layer)
# ---------------------------------------------------------------------------

class RuleCategoryEnum(str, Enum):
    coding = "coding"
    architecture = "architecture"
    testing = "testing"
    git = "git"
    forbidden = "forbidden"


class SkillTriggerEnum(str, Enum):
    auto_after_coding = "auto_after_coding"
    auto_before_pr = "auto_before_pr"
    manual = "manual"


class StoryStatusEnum(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class RoundTypeEnum(str, Enum):
    initial = "initial"
    iterate = "iterate"
    restart = "restart"


class RoundStatusEnum(str, Enum):
    created = "created"
    clarifying = "clarifying"
    planning = "planning"
    coding = "coding"
    pr_created = "pr_created"
    reviewing = "reviewing"
    revising = "revising"
    testing = "testing"
    done = "done"


class PRStatusEnum(str, Enum):
    open = "open"
    closed = "closed"
    merged = "merged"


# ---------------------------------------------------------------------------
# Project schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    repo_url: str
    description: str | None = None
    tech_stack: str | None = None
    architecture: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    description: str | None = None
    tech_stack: str | None = None
    architecture: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    repo_url: str
    description: str | None = None
    tech_stack: str | None = None
    architecture: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Story schemas
# ---------------------------------------------------------------------------

class StoryCreate(BaseModel):
    project_id: str
    title: str
    requirement: str
    requirement_source: str | None = None
    requirement_id: str | None = None
    acceptance_criteria: str | None = None


class StoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    requirement: str
    requirement_source: str | None = None
    requirement_id: str | None = None
    acceptance_criteria: str | None = None
    status: StoryStatusEnum
    current_round: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Round schemas
# ---------------------------------------------------------------------------

class RoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    story_id: str
    round_number: int
    type: RoundTypeEnum
    requirement_snapshot: str | None = None
    branch_name: str | None = None
    pr_id: str | None = None
    pr_status: PRStatusEnum | None = None
    close_reason: str | None = None
    status: RoundStatusEnum
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Rule schemas
# ---------------------------------------------------------------------------

class RuleCreate(BaseModel):
    project_id: str
    category: RuleCategoryEnum
    content: str
    enabled: bool = True


# ---------------------------------------------------------------------------
# Skill schemas
# ---------------------------------------------------------------------------

class SkillCreate(BaseModel):
    project_id: str
    name: str
    description: str | None = None
    command: str
    trigger: SkillTriggerEnum


# ---------------------------------------------------------------------------
# Action request schemas
# ---------------------------------------------------------------------------

class AnswerRequest(BaseModel):
    answers: dict[str, str] = Field(
        ..., description="Map of clarification ID to answer text"
    )


class ReviseRequest(BaseModel):
    feedback: str = Field(
        ..., description="Review feedback or revision instructions"
    )


class NewRoundRequest(BaseModel):
    type: RoundTypeEnum = Field(
        ..., description="Type of the new round (iterate or restart)"
    )
    requirement: str | None = Field(
        None, description="Updated requirement text for the new round"
    )


class ConfirmPlanRequest(BaseModel):
    confirmed: bool = Field(
        True, description="Whether the user confirms the proposed plan"
    )
    feedback: str | None = Field(
        None, description="Optional feedback if the plan is not confirmed"
    )


class RevisionRequest(BaseModel):
    mode: str = Field(
        ..., description="Revision mode: 'comments' or 'prompt'"
    )
    prompt: str | None = Field(
        None, description="Revision prompt when mode is 'prompt'"
    )


class TestRequest(BaseModel):
    pass


class MergeRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Clarification schemas
# ---------------------------------------------------------------------------

class ClarificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    round_id: str
    question: str
    answer: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# AIMessage schemas
# ---------------------------------------------------------------------------

class AIMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    round_id: str
    role: str
    content: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Rule / Skill response schemas
# ---------------------------------------------------------------------------

class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    category: RuleCategoryEnum
    content: str
    enabled: bool
    created_at: datetime


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    description: str | None = None
    command: str
    trigger: SkillTriggerEnum
    created_at: datetime


# ---------------------------------------------------------------------------
# Detailed response schemas (with nested relations)
# ---------------------------------------------------------------------------

class RoundDetailResponse(RoundResponse):
    clarifications: list[ClarificationResponse] = []


class StoryDetailResponse(StoryResponse):
    rounds: list[RoundDetailResponse] = []


class ProjectDetailResponse(ProjectResponse):
    rules: list[RuleResponse] = []
    skills: list[SkillResponse] = []
