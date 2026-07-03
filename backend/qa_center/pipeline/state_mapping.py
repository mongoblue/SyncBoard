"""State mappings between CI-platform statuses and the canonical PipelineRun status.

Every CI platform has its own status vocabulary.  This module maps each
platform’s statuses onto the canonical set used by PipelineRun.status:

    queued / running / passed / failed / cancelled / skipped

It also defines TERMINAL_STATUSES — once a run reaches one of these the
poller stops.
"""

from __future__ import annotations

# Canonical statuses used in PipelineRun
CANONICAL_QUEUED = "queued"
CANONICAL_RUNNING = "running"
CANONICAL_PASSED = "passed"
CANONICAL_FAILED = "failed"
CANONICAL_CANCELLED = "cancelled"
CANONICAL_SKIPPED = "skipped"

# ---------------------------------------------------------------------------
# Jenkins statuses (6)
# ---------------------------------------------------------------------------

# https://www.jenkins.io/doc/book/blueocean-api/#pipeline-node-status
_JENKINS_MAP: dict[str, str] = {
    "QUEUED": CANONICAL_QUEUED,
    "RUNNING": CANONICAL_RUNNING,
    "PAUSED": CANONICAL_RUNNING,          # treat paused as still running
    "SUCCESS": CANONICAL_PASSED,
    "UNSTABLE": CANONICAL_PASSED,         # unstable = tests failed but build ok → passed
    "NOT_BUILT": CANONICAL_SKIPPED,
    "ABORTED": CANONICAL_CANCELLED,
    "FAILURE": CANONICAL_FAILED,
}

def jenkins_to_canonical(jenkins_status: str) -> str:
    """Map a Jenkins pipeline status to the canonical status."""
    return _JENKINS_MAP.get(jenkins_status.upper(), CANONICAL_FAILED)


# ---------------------------------------------------------------------------
# GitLab CI statuses (9)
# ---------------------------------------------------------------------------

# https://docs.gitlab.com/ee/api/pipelines.html
_GITLAB_MAP: dict[str, str] = {
    "created": CANONICAL_QUEUED,
    "waiting_for_resource": CANONICAL_QUEUED,
    "preparing": CANONICAL_QUEUED,
    "pending": CANONICAL_QUEUED,
    "running": CANONICAL_RUNNING,
    "success": CANONICAL_PASSED,
    "failed": CANONICAL_FAILED,
    "canceled": CANONICAL_CANCELLED,
    "skipped": CANONICAL_SKIPPED,
    "manual": CANONICAL_RUNNING,           # waiting for manual action → still running
    "scheduled": CANONICAL_QUEUED,
}

def gitlab_to_canonical(gitlab_status: str) -> str:
    """Map a GitLab pipeline status to the canonical status."""
    return _GITLAB_MAP.get(gitlab_status.lower(), CANONICAL_FAILED)


# ---------------------------------------------------------------------------
# GitHub Actions statuses
# ---------------------------------------------------------------------------

# https://docs.github.com/en/rest/actions/workflow-runs
_GITHUB_MAP: dict[str, str] = {
    "queued": CANONICAL_QUEUED,
    "in_progress": CANONICAL_RUNNING,
    "pending": CANONICAL_QUEUED,
    "waiting": CANONICAL_QUEUED,
    "requested": CANONICAL_QUEUED,
}


def github_to_canonical(status: str, conclusion: str = "") -> str:
    """Map GitHub Actions workflow run status + conclusion to canonical status.

    GitHub returns two fields: ``status`` (queued/in_progress/completed) and
    ``conclusion`` (success/failure/cancelled/skipped/…).  When status is
    ``completed``, the conclusion determines the canonical result.
    """
    if not status:
        return CANONICAL_FAILED

    s = status.lower()
    if s in _GITHUB_MAP:
        return _GITHUB_MAP[s]

    if s == "completed":
        c = (conclusion or "").lower()
        if c == "success":
            return CANONICAL_PASSED
        if c == "failure":
            return CANONICAL_FAILED
        if c == "cancelled":
            return CANONICAL_CANCELLED
        if c == "skipped":
            return CANONICAL_SKIPPED
        return CANONICAL_FAILED

    return CANONICAL_FAILED


# ---------------------------------------------------------------------------
# Terminal statuses — poller stops when one of these is reached
# ---------------------------------------------------------------------------

TERMINAL_STATUSES: frozenset[str] = frozenset({
    CANONICAL_PASSED,
    CANONICAL_FAILED,
    CANONICAL_CANCELLED,
    CANONICAL_SKIPPED,
})
