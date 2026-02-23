"""Workspace utilities: path resolution, doc I/O, git clone, branch management."""

from opd.engine.workspace.git import (
    checkout_branch,
    clone_workspace,
    create_coding_branch,
    discard_branch,
    generate_branch_name,
)
from opd.engine.workspace.paths import (
    DOC_FIELD_MAP,
    DOC_FILENAME_MAP,
    delete_doc,
    list_docs,
    read_doc,
    resolve_work_dir,
    story_docs_dir,
    story_docs_relpath,
    story_slug,
    write_doc,
)
from opd.engine.workspace.scanner import scan_workspace

__all__ = [
    "DOC_FIELD_MAP",
    "DOC_FILENAME_MAP",
    "checkout_branch",
    "clone_workspace",
    "create_coding_branch",
    "delete_doc",
    "discard_branch",
    "generate_branch_name",
    "list_docs",
    "read_doc",
    "resolve_work_dir",
    "scan_workspace",
    "story_docs_dir",
    "story_docs_relpath",
    "story_slug",
    "write_doc",
]
