"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    """Request to create a new project."""

    name: str
    repo_url: str
    description: str = ""


class CreateStoryRequest(BaseModel):
    """Request to create a new story."""

    project_id: int
    title: str
    requirement: str


class AnswerRequest(BaseModel):
    """Request to answer a clarification question."""

    answer: str


class ProjectResponse(BaseModel):
    """Project response model."""

    id: int
    name: str
    repo_url: str
    description: str = ""

    model_config = {"from_attributes": True}


class StoryResponse(BaseModel):
    """Story response model."""

    id: int
    project_id: int
    title: str
    requirement: str
    status: str

    model_config = {"from_attributes": True}


class CapabilityStatusResponse(BaseModel):
    """Health status of a capability."""

    name: str
    healthy: bool
    message: str = ""
