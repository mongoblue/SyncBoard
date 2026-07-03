"""GitHub Actions CI client — trigger workflows, poll status, fetch logs.

Uses the GitHub REST API v3 for workflow runs.
ci_job_name supports either a workflow file name (e.g. 'ci.yml') or a
numeric workflow id.
"""

from __future__ import annotations

import io
import logging
import zipfile
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import CiClient, CiTriggerResult, CiRunStatus, CiJobResult
from .state_mapping import (
    github_to_canonical,
    CANONICAL_FAILED,
    TERMINAL_STATUSES,
)

logger = logging.getLogger(__name__)

_MAX_LOG_BYTES = 65536


class GitHubActionsClient(CiClient):
    """GitHub Actions CI/CD integration via GitHub REST API v3."""

    platform = "github_actions"

    def __init__(self, config):
        super().__init__(config)
        self._session: Optional[requests.Session] = None
        # ci_project = "owner/repo"
        self._owner, self._repo = self._parse_repo(self.project_path)
        # ci_job_name = workflow file name or numeric workflow id
        self._workflow = (config.ci_job_name or "").strip()

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
        """Trigger a workflow via the workflow dispatch API.

        POST /repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches
        """
        session = self._get_session()
        workflow_id = self._resolve_workflow_id(session)
        url = self._api_url(
            f"repos/{self._owner}/{self._repo}/actions/workflows/{workflow_id}/dispatches"
        )

        payload: dict = {"ref": ref}
        if variables:
            payload["inputs"] = dict(variables)
        payload.setdefault("inputs", {})["TRIGGER_SOURCE"] = trigger_source

        try:
            resp = session.post(url, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("GitHub trigger failed for %s/%s: %s",
                         self._owner, self._repo, _safe_error(exc))
            raise

        # The dispatch API returns 204 No Content — no run ID in response.
        # We must poll the runs list to find the newly created run.
        run_id = self._find_latest_run(session, workflow_id, ref, trigger_source)
        return CiTriggerResult(
            external_run_id=run_id,
            external_url=(
                f"https://github.com/{self._owner}/{self._repo}/actions/runs/{run_id}"
                if run_id else ""
            ),
        )

    # ------------------------------------------------------------------
    # get_status
    # ------------------------------------------------------------------

    def get_status(self, run) -> CiRunStatus:
        session = self._get_session()
        external_id = run.external_run_id
        url = self._api_url(
            f"repos/{self._owner}/{self._repo}/actions/runs/{external_id}"
        )
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            status = github_to_canonical(
                data.get("status", ""), data.get("conclusion", "")
            )
            return CiRunStatus(
                status=status,
                external_run_id=external_id,
                external_url=data.get("html_url", run.external_url or ""),
            )
        except requests.RequestException as exc:
            logger.error("GitHub get_status failed: %s", _safe_error(exc))
            return CiRunStatus(
                status=run.status,
                external_run_id=external_id,
                external_url=run.external_url or "",
                error=str(exc)[:200],
            )

    # ------------------------------------------------------------------
    # get_jobs
    # ------------------------------------------------------------------

    def get_jobs(self, run) -> List[CiJobResult]:
        session = self._get_session()
        external_id = run.external_run_id
        url = self._api_url(
            f"repos/{self._owner}/{self._repo}/actions/runs/{external_id}/jobs"
        )
        jobs: List[CiJobResult] = []
        try:
            params = {"per_page": 100}
            for _ in range(5):
                resp = session.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                for job in data.get("jobs", []):
                    jobs.append(CiJobResult(
                        name=job.get("name", ""),
                        status=github_to_canonical(
                            job.get("status", ""), job.get("conclusion", "")
                        ),
                        duration_ms=_parse_duration_ms(job),
                        external_job_id=str(job.get("id", "")),
                        external_url=job.get("html_url", ""),
                    ))
                next_link = resp.links.get("next", {}).get("url")
                if not next_link:
                    break
                url = next_link
                params = {}
        except requests.RequestException as exc:
            logger.error("GitHub get_jobs failed: %s", _safe_error(exc))
        return jobs

    # ------------------------------------------------------------------
    # get_logs
    # ------------------------------------------------------------------

    def get_logs(self, run, *, max_bytes: int = _MAX_LOG_BYTES) -> str:
        """Fetch and decompress workflow run logs.

        GitHub returns a zip archive via redirect.  We download, decompress,
        and concatenate all text files.  Output is sanitised to redact tokens.
        """
        session = self._get_session()
        external_id = run.external_run_id
        try:
            resp = session.get(
                self._api_url(
                    f"repos/{self._owner}/{self._repo}/actions/runs/{external_id}/logs"
                ),
                timeout=30, allow_redirects=False,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_url = resp.headers.get("Location", "")
                if not redirect_url:
                    return "[error] No redirect URL in logs response"
                # Use a bare requests.get (NOT session.get) to avoid leaking
                # the Authorization header to the third-party storage URL.
                import requests as _requests
                resp2 = _requests.get(redirect_url, timeout=60, stream=True)
                resp2.raise_for_status()
                zip_bytes = io.BytesIO()
                total = 0
                for chunk in resp2.iter_content(chunk_size=8192):
                    if chunk:
                        zip_bytes.write(chunk)
                        total += len(chunk)
                        if total > max_bytes * 2:
                            break
                zip_bytes.seek(0)
                logs = self._extract_zip_logs(zip_bytes, max_bytes)
            else:
                resp.raise_for_status()
                logs = resp.text[:max_bytes]
        except requests.RequestException as exc:
            logger.error("GitHub get_logs failed: %s", _safe_error(exc))
            return f"[error] {_safe_error(exc)}"

        # Sanitise: redact tokens from log output
        from .sanitize import sanitize_logs
        return sanitize_logs(logs)

    # ------------------------------------------------------------------
    # cancel
    # ------------------------------------------------------------------

    def cancel(self, run) -> bool:
        session = self._get_session()
        external_id = run.external_run_id
        url = self._api_url(
            f"repos/{self._owner}/{self._repo}/actions/runs/{external_id}/cancel"
        )
        try:
            resp = session.post(url, timeout=15)
            return resp.status_code in (200, 202, 204)
        except requests.RequestException as exc:
            logger.error("GitHub cancel failed: %s", _safe_error(exc))
            return False

    # ------------------------------------------------------------------
    # ping
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        """Check connectivity via GET /repos/{owner}/{repo}."""
        session = self._get_session()
        url = self._api_url(f"repos/{self._owner}/{self._repo}")
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "detail": data.get("full_name", f"{self._owner}/{self._repo}")}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)[:200]}

    # ------------------------------------------------------------------
    # verify_webhook
    # ------------------------------------------------------------------

    def verify_webhook(self, request) -> bool:
        """GitHub webhooks use X-Hub-Signature-256.  Verified at the view layer."""
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _api_url(self, path: str) -> str:
        base = self.base_url.rstrip("/")
        if not base.endswith("/"):
            base += "/"
        return urljoin(base, path.lstrip("/"))

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        s = requests.Session()
        s.verify = self.verify_ssl
        h = self._headers()
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        h["Accept"] = "application/vnd.github+json"
        h["X-GitHub-Api-Version"] = "2022-11-28"
        s.headers.update(h)
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        self._session = s
        return s

    @staticmethod
    def _parse_repo(project_path: str) -> tuple:
        parts = (project_path or "unknown/repo").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return parts[0], ""

    def _resolve_workflow_id(self, session) -> str:
        """Resolve ci_job_name to a numeric workflow id if it's a filename."""
        wf = self._workflow
        if wf.isdigit():
            return wf
        # Treat as filename — look up workflow ID
        url = self._api_url(
            f"repos/{self._owner}/{self._repo}/actions/workflows"
        )
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for w in data.get("workflows", []):
                if w.get("path", "").endswith(wf) or w.get("name", "") == wf:
                    return str(w["id"])
        except requests.RequestException as exc:
            logger.warning("Could not resolve workflow '%s': %s", wf, _safe_error(exc))
        return wf  # fall back to raw value

    def _find_latest_run(self, session, workflow_id, ref, trigger_source) -> str:
        """After dispatching, find the newly created run by polling the runs list.

        Filters by event=workflow_dispatch, branch, and creation time to avoid
        matching a run from a different dispatch.
        """
        import time as _time
        dispatch_time = _time.time()
        url = self._api_url(
            f"repos/{self._owner}/{self._repo}/actions/workflows/{workflow_id}/runs"
        )
        deadline = dispatch_time + 30
        while _time.time() < deadline:
            try:
                resp = session.get(
                    url,
                    params={
                        "per_page": 5,
                        "branch": ref,
                        "event": "workflow_dispatch",
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                runs = data.get("workflow_runs", [])
                for run in runs:
                    created = run.get("created_at", "")
                    if created:
                        try:
                            from datetime import datetime, timezone as _tz
                            created_ts = datetime.strptime(
                                created, "%Y-%m-%dT%H:%M:%SZ"
                            ).replace(tzinfo=_tz.utc).timestamp()
                        except (ValueError, TypeError):
                            created_ts = 0
                        # Only accept runs created AFTER our dispatch
                        if created_ts >= dispatch_time - 5:
                            return str(run["id"])
                # No matching run yet — wait and retry
            except requests.RequestException:
                pass
            _time.sleep(2)
        return ""

    def _extract_zip_logs(self, zip_bytes: io.BytesIO, max_bytes: int) -> str:
        try:
            parts = []
            total = 0
            with zipfile.ZipFile(zip_bytes, 'r') as zf:
                for name in sorted(zf.namelist()):
                    with zf.open(name) as f:
                        text = f.read().decode("utf-8", errors="replace")
                        parts.append(f"--- {name} ---\n")
                        parts.append(text)
                        parts.append("\n")
                        total += len(text)
                        if total >= max_bytes:
                            parts.append("\n... [truncated]\n")
                            break
            return self._truncate_logs("".join(parts), max_bytes)
        except (zipfile.BadZipFile, Exception) as exc:
            return f"[error] Could not extract logs zip: {_safe_error(exc)}"


# ── helpers ─────────────────────────────────────────────────────────────


def _safe_error(exc: Exception) -> str:
    """Return exc message truncated, with no token leakage."""
    msg = str(exc)
    if len(msg) > 200:
        msg = msg[:197] + "..."
    return msg


def _parse_duration_ms(job: dict) -> Optional[int]:
    """Parse GitHub job timestamps into duration in milliseconds."""
    started = job.get("started_at")
    completed = job.get("completed_at")
    if started and completed:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            s = datetime.strptime(started, fmt)
            e = datetime.strptime(completed, fmt)
            return int((e - s).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass
    return None
