"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    name: str
    repo_url: str
    description: str = ""
    tech_stack: str = ""
    architecture: str = ""


class CreateStoryRequest(BaseModel):
    title: str
    raw_input: str
    feature_tag: str | None = None


class QAPair(BaseModel):
    question: str
    answer: str


class AnswerRequest(BaseModel):
    answers: list[QAPair]


class CapabilityStatusResponse(BaseModel):
    name: str
    healthy: bool
    message: str = ""


class SaveCapabilityConfigRequest(BaseModel):
    enabled: bool = True
    provider_override: str | None = None
    config_override: dict | None = None


class TestCapabilityRequest(BaseModel):
    provider: str
    config: dict
