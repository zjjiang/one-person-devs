"""Database models for OPD v2."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --- Enums ---


class StoryStatus(str, enum.Enum):
    preparing = "preparing"
    clarifying = "clarifying"
    planning = "planning"
    designing = "designing"
    coding = "coding"
    verifying = "verifying"
    done = "done"


class RoundType(str, enum.Enum):
    initial = "initial"
    iterate = "iterate"
    restart = "restart"


class RoundStatus(str, enum.Enum):
    active = "active"
    closed = "closed"


class PRStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    merged = "merged"


class AIMessageRole(str, enum.Enum):
    assistant = "assistant"
    tool = "tool"
    user = "user"


class RuleCategory(str, enum.Enum):
    coding = "coding"
    architecture = "architecture"
    testing = "testing"
    git = "git"
    forbidden = "forbidden"


class SkillTrigger(str, enum.Enum):
    auto_after_coding = "auto_after_coding"
    auto_before_pr = "auto_before_pr"
    manual = "manual"


class WorkspaceStatus(str, enum.Enum):
    pending = "pending"
    cloning = "cloning"
    ready = "ready"
    error = "error"


# --- Models ---


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tech_stack: Mapped[str] = mapped_column(Text, default="")
    architecture: Mapped[str] = mapped_column(Text, default="")
    workspace_dir: Mapped[str] = mapped_column(String(500), default="")
    workspace_status: Mapped[WorkspaceStatus] = mapped_column(
        Enum(WorkspaceStatus), default=WorkspaceStatus.pending
    )
    workspace_error: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    rules: Mapped[list[Rule]] = relationship(back_populates="project", cascade="all, delete-orphan")
    skills: Mapped[list[Skill]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    stories: Mapped[list[Story]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    capability_configs: Mapped[list[ProjectCapabilityConfig]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    category: Mapped[RuleCategory] = mapped_column(Enum(RuleCategory), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="rules")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    command: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[SkillTrigger] = mapped_column(Enum(SkillTrigger), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="skills")


class ProjectCapabilityConfig(Base):
    __tablename__ = "project_capability_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    capability: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    provider_override: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped[Project] = relationship(back_populates="capability_configs")


class GlobalCapabilityConfig(Base):
    __tablename__ = "global_capability_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capability: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    feature_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[StoryStatus] = mapped_column(
        Enum(StoryStatus), default=StoryStatus.preparing
    )
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    # Stage outputs
    raw_input: Mapped[str] = mapped_column(Text, default="")
    prd: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_prd: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_design: Mapped[str | None] = mapped_column(Text, nullable=True)
    detailed_design: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="stories")
    tasks: Mapped[list[Task]] = relationship(back_populates="story", cascade="all, delete-orphan")
    rounds: Mapped[list[Round]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    clarifications: Mapped[list[Clarification]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped[Story] = relationship(back_populates="tasks")


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[RoundType] = mapped_column(Enum(RoundType), default=RoundType.initial)
    branch_name: Mapped[str] = mapped_column(String(200), default="")
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RoundStatus] = mapped_column(Enum(RoundStatus), default=RoundStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    story: Mapped[Story] = relationship(back_populates="rounds")
    pull_requests: Mapped[list[PullRequest]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )
    ai_messages: Mapped[list[AIMessage]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[PRStatus] = mapped_column(Enum(PRStatus), default=PRStatus.open)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    round: Mapped[Round] = relationship(back_populates="pull_requests")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), nullable=False)
    role: Mapped[AIMessageRole] = mapped_column(Enum(AIMessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    round: Mapped[Round] = relationship(back_populates="ai_messages")


class Clarification(Base):
    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped[Story] = relationship(back_populates="clarifications")
