from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


def _generate_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

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


class StoryStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class RoundType(str, enum.Enum):
    initial = "initial"
    iterate = "iterate"
    restart = "restart"


class RoundStatus(str, enum.Enum):
    created = "created"
    clarifying = "clarifying"
    planning = "planning"
    coding = "coding"
    pr_created = "pr_created"
    reviewing = "reviewing"
    revising = "revising"
    testing = "testing"
    done = "done"


class PRStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    merged = "merged"


class AIMessageRole(str, enum.Enum):
    assistant = "assistant"
    tool = "tool"
    user = "user"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    architecture: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rules: Mapped[list[Rule]] = relationship(
        "Rule", back_populates="project", cascade="all, delete-orphan"
    )
    skills: Mapped[list[Skill]] = relationship(
        "Skill", back_populates="project", cascade="all, delete-orphan"
    )
    stories: Mapped[list[Story]] = relationship(
        "Story", back_populates="project", cascade="all, delete-orphan"
    )


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[RuleCategory] = mapped_column(
        Enum(RuleCategory), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship("Project", back_populates="rules")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[SkillTrigger] = mapped_column(
        Enum(SkillTrigger), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship("Project", back_populates="skills")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_source: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    requirement_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[StoryStatus] = mapped_column(
        Enum(StoryStatus), default=StoryStatus.pending, nullable=False
    )
    current_round: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship("Project", back_populates="stories")
    rounds: Mapped[list[Round]] = relationship(
        "Round", back_populates="story", cascade="all, delete-orphan"
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[RoundType] = mapped_column(Enum(RoundType), nullable=False)
    requirement_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pr_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pr_status: Mapped[Optional[PRStatus]] = mapped_column(
        Enum(PRStatus), nullable=True
    )
    close_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[RoundStatus] = mapped_column(
        Enum(RoundStatus), default=RoundStatus.created, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    story: Mapped[Story] = relationship("Story", back_populates="rounds")
    clarifications: Mapped[list[Clarification]] = relationship(
        "Clarification", back_populates="round", cascade="all, delete-orphan"
    )
    ai_messages: Mapped[list[AIMessage]] = relationship(
        "AIMessage", back_populates="round", cascade="all, delete-orphan"
    )


class Clarification(Base):
    __tablename__ = "clarifications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    round: Mapped[Round] = relationship("Round", back_populates="clarifications")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[AIMessageRole] = mapped_column(
        Enum(AIMessageRole), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    round: Mapped[Round] = relationship("Round", back_populates="ai_messages")
