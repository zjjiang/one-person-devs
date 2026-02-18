"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class CreateProjectRequest(BaseModel):
    name: str
    repo_url: str
    description: str = ""
    tech_stack: str = ""
    architecture: str = ""
    workspace_dir: str = ""

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repo_url is required")
        if not (
            v.startswith("https://") or v.startswith("http://")
            or v.startswith("git@") or v.startswith("ssh://")
        ):
            raise ValueError("repo_url must be a valid git URL (https://, git@, ssh://)")
        return v


class CreateStoryRequest(BaseModel):
    title: str
    raw_input: str
    feature_tag: str | None = None


class QAPair(BaseModel):
    id: int | None = None
    question: str
    answer: str


class AnswerRequest(BaseModel):
    answers: list[QAPair]


class CapabilityStatusResponse(BaseModel):
    name: str
    healthy: bool
    message: str = ""


class SaveCapabilityConfigRequest(BaseModel):
    capability: str = ""  # Used by batch endpoint
    enabled: bool = True
    provider_override: str | None = None
    config_override: dict | None = None


class TestCapabilityRequest(BaseModel):
    provider: str
    config: dict


class UpdatePrdRequest(BaseModel):
    prd: str


class ChatRequest(BaseModel):
    message: str


class UpdateDocRequest(BaseModel):
    content: str


class RollbackRequest(BaseModel):
    target_stage: str

    @field_validator("target_stage")
    @classmethod
    def validate_target_stage(cls, v: str) -> str:
        allowed = {"preparing", "clarifying", "planning", "designing"}
        if v not in allowed:
            raise ValueError(f"target_stage must be one of {allowed}")
        return v
