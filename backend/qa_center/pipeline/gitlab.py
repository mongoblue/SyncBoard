"""GitLab CI client — trigger pipelines, poll status, fetch job logs.

Uses the GitLab REST API v4.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin, quote_plus

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import CiClient, CiTriggerResult, CiRunStatus, CiJobResult
from .state_mapping import (
    gitlab_to_canonical,
    CANONICAL_FAILED,
    TERMINAL_STATUSES,
)

logger = logging.getLogger(__name__)

_MAX_LOG_BYTES = 65536


class GitLabClient(CiClient):
    """GitLab CI/CD integration via GitLab API v4."""

    platform = "gitlab"

    def __init__(self, config):
        super().__init__(config)
        self._session: Optional[requests.Session] = None
        # Project ID can be numeric or URL-encoded path
        self._project_id: str = self.project_path

    # ------------------------------------------------------------------
    # trigger
    # ------------------------------------------------------------------

    def trigger(
        self,
        config,
        *,
        ref: str = "main",
        variables: Optional[Dict[str, str]] = None,
        trigger_source: str = "qa_center",
    ) -> CiTriggerResult:
        """Trigger a new GitLab pipeline via POST /projects/:id/pipeline."""
        session = self._get_session()
        api_url = self._api_url(f"projects/{quote_plus(self._project_id)}/pipeline")

        payload: dict = {"ref": ref}
        if variables:
            var_list = [{"key": k, "value": v} for k, v in variables.items()]
            var_list.append({"key": "TRIGGER_SOURCE", "value": trigger_source})
            payload["variables"] = var_list

        try:
            resp = session.post(api_url, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("GitLab trigger failed for project %s: %s", self._project_id, exc)
            raise

        data = resp.json()
        run_id = str(data.get("id", ""))
        return CiTriggerResult(
            external_run_id=run_id,
            external_url=data.get("web_url", ""),
        )

    # ------------------------------------------------------------------
    # get_status
    # ------------------------------------------------------------------

    def get_status(self, run) -> CiRunStatus:
        session = self._get_session()
        external_id = run.external_run_id
        api_url = self._api_url(
            f"projects/{quote_plus(self._project_id)}/pipelines/{external_id}"
        )
        try:
            resp = session.get(api_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            status = gitlab_to_canonical(data.get("status", "failed"))
            return CiRunStatus(
                status=status,
                external_run_id=external_id,
                external_url=data.get("web_url", run.external_url or ""),
                duration_ms=data.get("duration"),
            )
        except requests.RequestException as exc:
            logger.error("GitLab get_status failed: %s", exc)
            return CiRunStatus(
                status=run.status,
                external_run_id=external_id,
                external_url=run.external_url or "",
                error=str(exc)[:500],
            )

    # ------------------------------------------------------------------
    # get_jobs
    # ------------------------------------------------------------------

    def get_jobs(self, run) -> List[CiJobResult]:
        session = self._get_session()
        external_id = run.external_run_id
        api_url = self._api_url(
            f"projects/{quote_plus(self._project_id)}/pipelines/{external_id}/jobs"
        )
        jobs: List[CiJobResult] = []
        try:
            # GitLab paginates — collect all pages (capped)
            params = {"per_page": 100}
            for _ in range(5):  # max 500 jobs
                resp = session.get(api_url, params=params, timeout=15)
                resp.raise_for_status()
                page_data = resp.json()
                for job in page_data:
                    jobs.append(CiJobResult(
                        name=job.get("name", ""),
                        stage=job.get("stage", ""),
                        status=gitlab_to_canonical(job.get("status", "unknown")),
                        duration_ms=int(job["duration"] * 1000) if job.get("duration") else None,
                        external_job_id=str(job.get("id", "")),
                        external_url=job.get("web_url", ""),
                    ))
                # Check for next page
                next_link = resp.links.get("next", {}).get("url")
                if not next_link:
                    break
                # Use next_link directly but still cap params
                api_url = next_link
                params = {}
        except requests.RequestException as exc:
            logger.error("GitLab get_jobs failed: %s", exc)
        return jobs

    # ------------------------------------------------------------------
    # get_logs
    # ------------------------------------------------------------------

    def get_logs(self, run, *, max_bytes: int = _MAX_LOG_BYTES) -> str:
        """Fetch combined logs from all jobs in the pipeline."""
        jobs = self.get_jobs(run)
        if not jobs:
            return "[no jobs found]"

        session = self._get_session()
        all_logs: List[str] = []
        total_bytes = 0

        for job in jobs:
            if total_bytes >= max_bytes:
                break
            if not job.external_job_id:
                continue
            log_url = self._api_url(
                f"projects/{quote_plus(self._project_id)}/jobs/{job.external_job_id}/trace"
            )
            try:
                resp = session.get(log_url, timeout=30, stream=True)
                resp.raise_for_status()
                all_logs.append(f"--- {job.name} ({job.stage}) ---\n")
                for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
                    if chunk:
                        text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace")
                        all_logs.append(text)
                        total_bytes += len(text)
                        if total_bytes >= max_bytes:
                            break
                all_logs.append("\n")
            except requests.RequestException as exc:
                all_logs.append(f"[error] {job.name}: {exc}\n")

        from .sanitize import sanitize_logs
        return sanitize_logs(self._truncate_logs("".join(all_logs), max_bytes))

    # ------------------------------------------------------------------
    # cancel
    # ------------------------------------------------------------------

    def cancel(self, run) -> bool:
        session = self._get_session()
        external_id = run.external_run_id
        api_url = self._api_url(
            f"projects/{quote_plus(self._project_id)}/pipelines/{external_id}/cancel"
        )
        try:
            resp = session.post(api_url, timeout=15)
            return resp.status_code in (200, 201)
        except requests.RequestException as exc:
            logger.error("GitLab cancel failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # verify_webhook
    # ------------------------------------------------------------------

    def verify_webhook(self, request) -> bool:
        """Verify GitLab webhook via X-Gitlab-Token header."""
        expected = self.token
        if not expected:
            return True
        provided = request.headers.get("X-Gitlab-Token", "").strip()
        import hmac
        return hmac.compare_digest(provided, expected)

    # ------------------------------------------------------------------
    # ping
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        """Check GitLab connectivity via GET /api/v4/version."""
        session = self._get_session()
        url = self.base_url.rstrip("/") + "/api/v4/version"
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "detail": f"GitLab {data.get('version', 'unknown')}"}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)[:200]}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _api_url(self, path: str) -> str:
        """Build full GitLab API v4 URL."""
        base = self.base_url.rstrip("/")
        # GitLab API is at /api/v4/
        if not base.endswith("/api/v4"):
            base = base + "/api/v4"
        return urljoin(base + "/", path.lstrip("/"))

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        s = requests.Session()
        s.verify = self.verify_ssl
        h = self._headers()
        if self.token:
            h["PRIVATE-TOKEN"] = self.token
        s.headers.update(h)
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        self._session = s
        return s
