"""Webhook endpoints for external service integrations."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opd.api.deps import get_orchestrator, get_session
from opd.db.models import Round, RoundStatus
from opd.engine.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_github_signature(
    payload: bytes,
    signature: str | None,
    secret: str,
) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    if signature is None:
        return False
    expected = (
        "sha256="
        + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@router.post(
    "/github",
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook receiver (PR events)",
)
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
    orch: Orchestrator = Depends(get_orchestrator),
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, str]:
    """Handle incoming GitHub webhook events.

    Currently processes:
    - ``pull_request`` events (opened, closed, merged, review_requested)
    - ``pull_request_review`` events (submitted)

    Other events are acknowledged but ignored.
    """
    payload = await request.body()

    # Verify signature if webhook secret is configured
    scm_provider = orch.providers.get("scm")
    if scm_provider and hasattr(scm_provider, "config"):
        secret = scm_provider.config.get("webhook_secret", "")
        if secret and not _verify_github_signature(payload, x_hub_signature_256, secret):
            raise HTTPException(status_code=403, detail="Invalid signature")

    body: dict[str, Any] = await request.json()
    event = x_github_event or ""

    logger.info("Received GitHub webhook: event=%s", event)

    if event == "pull_request":
        await _handle_pr_event(db, orch, body)
    elif event == "pull_request_review":
        await _handle_pr_review_event(db, orch, body)
    else:
        logger.debug("Ignoring GitHub event: %s", event)

    return {"status": "ok"}


async def _handle_pr_event(
    db: AsyncSession,
    orch: Orchestrator,
    body: dict[str, Any],
) -> None:
    """Process a pull_request webhook event."""
    action = body.get("action", "")
    pr = body.get("pull_request", {})
    pr_number = str(pr.get("number", ""))

    logger.info("PR event: action=%s, pr=#%s", action, pr_number)

    # Find the round associated with this PR
    result = await db.execute(
        select(Round).where(Round.pr_id == pr_number)
    )
    round_ = result.scalar_one_or_none()
    if round_ is None:
        logger.debug("No round found for PR #%s, ignoring", pr_number)
        return

    if action == "closed" and pr.get("merged", False):
        # PR was merged externally
        if round_.status != RoundStatus.done:
            round_.status = RoundStatus.done
            await db.flush()
            logger.info("Round %s marked done (PR merged externally)", round_.id)

    elif action == "closed" and not pr.get("merged", False):
        # PR was closed without merging
        round_.close_reason = "PR closed without merge"
        if round_.status != RoundStatus.done:
            round_.status = RoundStatus.done
            await db.flush()
            logger.info("Round %s marked done (PR closed)", round_.id)


async def _handle_pr_review_event(
    db: AsyncSession,
    orch: Orchestrator,
    body: dict[str, Any],
) -> None:
    """Process a pull_request_review webhook event."""
    review = body.get("review", {})
    pr = body.get("pull_request", {})
    pr_number = str(pr.get("number", ""))
    review_state = review.get("state", "")

    logger.info(
        "PR review event: pr=#%s, state=%s", pr_number, review_state
    )

    result = await db.execute(
        select(Round).where(Round.pr_id == pr_number)
    )
    round_ = result.scalar_one_or_none()
    if round_ is None:
        logger.debug("No round found for PR #%s, ignoring", pr_number)
        return

    if review_state == "changes_requested":
        # Transition to reviewing if not already there
        if round_.status == RoundStatus.pr_created:
            round_.status = RoundStatus.reviewing
            await db.flush()
            logger.info(
                "Round %s transitioned to reviewing (changes requested)",
                round_.id,
            )
    elif review_state == "approved":
        logger.info("PR #%s approved, round %s", pr_number, round_.id)
        # The user can now trigger merge or test via the API
