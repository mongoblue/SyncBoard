"""Pipeline integration module — abstract CI client interface and factory.

Provides:
- CiClient ABC: standard interface for CI/CD platform integration
- CiTriggerResult/CiRunStatus/CiJobResult: typed result containers
- get_client(): factory that returns the right client for a CiCdConfig
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CiTriggerResult:
    """Result returned by a CI trigger call."""
    external_queue_id: Optional[str] = None
    external_run_id: str = ""
    external_url: str = ""
    extra: Dict = field(default_factory=dict)


@dataclass
class CiJobResult:
    """A single job within a pipeline run."""
    name: str
    stage: str = ""
    status: str = "unknown"
    duration_ms: Optional[int] = None
    external_job_id: Optional[str] = None
    external_url: str = ""
    log_preview: str = ""


@dataclass
class CiRunStatus:
    """Full status of a pipeline run."""
    status: str  # canonical status — see state_mapping.py
    jobs: List[CiJobResult] = field(default_factory=list)
    duration_ms: Optional[int] = None
    external_run_id: str = ""
    external_url: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class CiClient(abc.ABC):
    """Abstract CI/CD platform client.

    Each concrete implementation (Jenkins, GitLab, GitHub Actions, …)
    must implement all abstract methods.  Helper methods (e.g. _headers)
    may be overridden but sensible defaults are provided.
    """

    # Subclasses should set this for metrics / logging.
    platform: str = "generic"

    def __init__(self, config):
        """
        Parameters
        ----------
        config : CiCdConfig
            The Django model instance holding CI configuration.
        """
        self.config = config
        self.base_url: str = (config.ci_url or "").rstrip("/")
        self.token: str = (config.ci_token or "").strip()
        self.project_path: str = (config.ci_project or "").strip()
        self.job_name: str = (config.ci_job_name or "").strip()
        self.verify_ssl: bool = getattr(config, "verify_ssl", True)

    # -- required -----------------------------------------------------------

    @abc.abstractmethod
    def trigger(
        self,
        config,
        *,
        ref: str = "main",
        variables: Optional[Dict[str, str]] = None,
        trigger_source: str = "qa_center",
    ) -> CiTriggerResult:
        """Trigger a new pipeline / build.  Must be implemented."""

    @abc.abstractmethod
    def get_status(self, run) -> CiRunStatus:
        """Return current status for *run* (a PipelineRun instance)."""

    @abc.abstractmethod
    def get_jobs(self, run) -> List[CiJobResult]:
        """Return list of jobs for *run*."""

    @abc.abstractmethod
    def get_logs(self, run, *, max_bytes: int = 65536) -> str:
        """Return the raw / combined log output, truncated to *max_bytes*."""

    @abc.abstractmethod
    def cancel(self, run) -> bool:
        """Attempt to cancel the pipeline.  Returns True on success."""

    @abc.abstractmethod
    def verify_webhook(self, request) -> bool:
        """Verify an incoming webhook request is authentic.  Returns True/False."""

    # -- health check ---------------------------------------------------------

    def ping(self) -> dict:
        """Check connectivity to the CI platform.

        Returns a dict with ``ok`` (bool) and ``detail`` (str).
        Subclasses should override with platform-specific health checks.
        """
        return {"ok": False, "detail": f"ping() not implemented for {self.platform}"}

    # -- helpers ------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        """Return HTTP headers used for API calls."""
        return {"Accept": "application/json"}

    def _truncate_logs(self, text: str, max_bytes: int) -> str:
        if len(text) <= max_bytes:
            return text
        return text[:max_bytes - 3] + "…"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_client(config) -> CiClient:
    """Return the appropriate CiClient for *config*.

    Uses the feature flag USE_REAL_CI (defaults to False).  When False a
    no-op mock is returned that simulates successful pipeline runs.

    When USE_REAL_CI is True, selects based on config.ci_type.
    """
    if not getattr(settings, "USE_REAL_CI", False):
        return _MockCiClient(config)

    ci_type = (config.ci_type or "").lower()
    if ci_type == "jenkins":
        from .jenkins import JenkinsClient
        return JenkinsClient(config)
    if ci_type == "gitlab":
        from .gitlab import GitLabClient
        return GitLabClient(config)
    if ci_type in ("github", "github_actions"):
        from .github import GitHubActionsClient
        return GitHubActionsClient(config)
    # Fallback — other CI types can be added later
    logger.warning("No real CI client for type=%r; falling back to mock.", ci_type)
    return _MockCiClient(config)


# ---------------------------------------------------------------------------
# Mock client (used when USE_REAL_CI is False)
# ---------------------------------------------------------------------------

class _MockCiClient(CiClient):
    """Deterministic mock CI client for dev/local environments only.

    Never produces random results.  All responses are clearly marked as mock
    so consumers (quality reports, dashboards) can exclude them via
    PipelineRun.is_mock.
    """

    platform = "mock"

    def trigger(self, config, *, ref="main", variables=None, trigger_source="qa_center"):
        import uuid
        run_id = f"mock-{uuid.uuid4().hex[:12]}"
        return CiTriggerResult(
            external_queue_id=run_id,
            external_run_id=run_id,
            external_url=f"https://mock-ci.internal/runs/{run_id}",
        )

    def get_status(self, run) -> CiRunStatus:
        return CiRunStatus(
            status="passed",
            external_run_id=run.external_run_id or "",
            external_url=run.external_url or "",
            jobs=[
                CiJobResult(name="mock-job", stage="test", status="passed", duration_ms=0),
            ],
        )

    def get_jobs(self, run):
        return self.get_status(run).jobs

    def get_logs(self, run, *, max_bytes=65536):
        return "[MOCK] No real CI logs available — USE_REAL_CI=False."

    def cancel(self, run) -> bool:
        return True

    def verify_webhook(self, request) -> bool:
        # In strict environments, the mock client must never accept webhooks.
        # The real webhook endpoint already enforces this at the view layer,
        # but double-check here as a belt-and-suspenders safeguard.
        from qa_center.api_execution.runtime_guard import RuntimeGuard
        guard = RuntimeGuard()
        if guard.is_strict():
            logger.warning("[MOCK] verify_webhook called in strict env — rejecting")
            return False
        return True

    def ping(self) -> dict:
        return {"ok": True, "detail": "mock — USE_REAL_CI=False"}
