"""Input hash utilities for stage change detection."""

from __future__ import annotations

import hashlib
from typing import Any

from opd.engine.workspace import read_doc


def compute_hash(content: str) -> str:
    """Compute SHA-256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# Stage → (input doc field on Story, input doc filename, hash field on Story, output doc field)
STAGE_INPUT_MAP: dict[str, tuple[str, str, str, str]] = {
    "planning": ("confirmed_prd", "prd.md", "planning_input_hash", "technical_design"),
    "designing": ("technical_design", "technical_design.md", "designing_input_hash", "detailed_design"),
    "coding": ("detailed_design", "detailed_design.md", "coding_input_hash", "coding_report"),
}


def get_stage_input_content(story: Any, project: Any, stage: str) -> str | None:
    """Read the input content for a given stage.

    Tries the doc file first, falls back to the DB field.
    Returns None if no input content is available.
    """
    mapping = STAGE_INPUT_MAP.get(stage)
    if not mapping:
        return None
    field, filename, _, _ = mapping
    # Try reading from file first (doc fields store relative paths)
    content = read_doc(project, story, filename)
    if content:
        return content
    # Fallback to DB field value (might be inline content)
    val = getattr(story, field, None)
    if val and not val.startswith("docs/"):
        return val
    return None


def compute_stage_input_hash(story: Any, project: Any, stage: str) -> str | None:
    """Compute the input hash for a stage. Returns None if no input available."""
    content = get_stage_input_content(story, project, stage)
    return compute_hash(content) if content else None


def should_skip_ai(story: Any, project: Any, stage: str) -> bool:
    """Check if AI generation can be skipped for a stage.

    Returns True if the stage already has output AND the input hasn't changed.
    """
    mapping = STAGE_INPUT_MAP.get(stage)
    if not mapping:
        return False
    _, _, hash_field, output_field = mapping
    # Stage must have existing output
    if not getattr(story, output_field, None):
        return False
    # Must have a stored hash to compare against
    stored_hash = getattr(story, hash_field, None)
    if not stored_hash:
        return False
    # Compare current input hash with stored hash
    current_hash = compute_stage_input_hash(story, project, stage)
    return current_hash == stored_hash
