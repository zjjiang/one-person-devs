"""GitHub webhook handler."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/github")
async def github_webhook(request: Request):
    """Handle GitHub webhook events (PR reviews, status checks)."""
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    if event_type == "pull_request_review":
        action = payload.get("action")
        pr_number = payload.get("pull_request", {}).get("number")
        logger.info("PR review event: action=%s pr=%s", action, pr_number)
    elif event_type == "pull_request":
        action = payload.get("action")
        pr_number = payload.get("pull_request", {}).get("number")
        logger.info("PR event: action=%s pr=%s", action, pr_number)
    else:
        logger.debug("Ignoring webhook event: %s", event_type)

    return {"status": "ok"}
