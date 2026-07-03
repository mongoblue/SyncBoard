"""Jenkins CI client — trigger builds, poll status, fetch logs.

Uses the Jenkins Blue Ocean REST API (preferred) with a fallback to the
classic REST API for older Jenkins instances.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import CiClient, CiTriggerResult, CiRunStatus, CiJobResult
from .state_mapping import (
    jenkins_to_canonical,
    CANONICAL_QUEUED,
    CANONICAL_RUNNING,
    CANONICAL_FAILED,
    TERMINAL_STATUSES,
)

logger = logging.getLogger(__name__)

# Maximum poll time for queue resolution (Jenkins returns queue id first)
_QUEUE_POLL_MAX_SEC = 120
_QUEUE_POLL_INTERVAL_SEC = 2
_MAX_LOG_BYTES = 65536


class JenkinsClient(CiClient):
    """Jenkins CI integration via Blue Ocean / classic REST API."""

    platform = "jenkins"

    def __init__(self, config):
        super().__init__(config)
        self._session: Optional[requests.Session] = None

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
        """Trigger a Jenkins job and return queue/build ids.

        Strategy:
        1. POST to classic /job/{name}/buildWithParameters (or /build)
        2. Read Location header to get queue item URL
        3. Poll queue item until executable (build) appears
        """
        session = self._get_session()
        job_path = self._job_url()

        # Build URL for trigger
        trigger_url = urljoin(job_path + "/", "buildWithParameters" if variables else "build")
        params = {}
        if variables:
            params.update(variables)
        if ref:
            params.setdefault("BRANCH", ref)
        params["TRIGGER_SOURCE"] = trigger_source

        try:
            resp = session.post(trigger_url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Jenkins trigger failed for %s: %s", job_path, exc)
            raise

        # Jenkins returns queue item location in headers
        queue_url = resp.headers.get("Location", "")
        if not queue_url:
            logger.warning("Jenkins trigger: no Location header; response=%s", resp.text[:500])
            return CiTriggerResult(
                external_run_id="unknown",
                external_url=job_path,
            )

        # Poll the queue item until a build number is available
        queue_id = queue_url.rstrip("/").rsplit("/", 1)[-1]
        build_url = self._poll_queue(session, queue_url)
        if build_url is None:
            return CiTriggerResult(
                external_queue_id=queue_id,
                external_run_id=queue_id,
                external_url=job_path,
            )

        build_number = build_url.rstrip("/").rsplit("/", 1)[-1]
        return CiTriggerResult(
            external_queue_id=queue_id,
            external_run_id=build_number,
            external_url=build_url,
        )

    # ------------------------------------------------------------------
    # get_status
    # ------------------------------------------------------------------

    def get_status(self, run) -> CiRunStatus:
        """Return the current status of a pipeline run.

        Prefers Blue Ocean API: /blue/rest/organizations/jenkins/pipelines/…/runs/{id}/
        Falls back to classic API.
        """
        session = self._get_session()
        external_id = run.external_run_id

        # Try Blue Ocean first
        blue_url = urljoin(
            self.base_url + "/",
            f"blue/rest/organizations/jenkins/pipelines/{self.job_name}/runs/{external_id}/",
        )
        try:
            resp = session.get(blue_url, timeout=15)
            if resp.status_code == 200:
                return self._parse_blue_ocean_status(resp.json(), run)
        except (requests.RequestException, ValueError) as exc:
            logger.debug("Blue Ocean status failed, trying classic: %s", exc)

        # Fallback to classic API
        classic_url = urljoin(
            self._job_url() + "/",
            f"{external_id}/api/json",
        )
        try:
            resp = session.get(classic_url, timeout=15)
            resp.raise_for_status()
            return self._parse_classic_status(resp.json(), run)
        except requests.RequestException as exc:
            logger.error("Jenkins get_status failed: %s", exc)
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

        # Blue Ocean
        blue_url = urljoin(
            self.base_url + "/",
            f"blue/rest/organizations/jenkins/pipelines/{self.job_name}/runs/{external_id}/nodes/",
        )
        try:
            resp = session.get(blue_url, timeout=15)
            if resp.status_code == 200:
                return self._parse_blue_ocean_nodes(resp.json())
        except (requests.RequestException, ValueError):
            pass

        # Classic fallback is limited
        return []

    # ------------------------------------------------------------------
    # get_logs
    # ------------------------------------------------------------------

    def get_logs(self, run, *, max_bytes: int = _MAX_LOG_BYTES) -> str:
        session = self._get_session()
        external_id = run.external_run_id
        log_url = urljoin(
            self._job_url() + "/",
            f"{external_id}/consoleText",
        )
        try:
            resp = session.get(log_url, timeout=30, stream=True)
            resp.raise_for_status()
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
                if chunk:
                    chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace"))
                    total += len(chunks[-1])
                    if total >= max_bytes:
                        break
            text = "".join(chunks)
            from .sanitize import sanitize_logs
            return sanitize_logs(self._truncate_logs(text, max_bytes))
        except requests.RequestException as exc:
            logger.error("Jenkins get_logs failed: %s", exc)
            return f"[error] Failed to fetch logs: {exc}"

    # ------------------------------------------------------------------
    # cancel
    # ------------------------------------------------------------------

    def cancel(self, run) -> bool:
        session = self._get_session()
        external_id = run.external_run_id
        stop_url = urljoin(
            self._job_url() + "/",
            f"{external_id}/stop",
        )
        try:
            resp = session.post(stop_url, timeout=15)
            return resp.status_code in (200, 201, 204, 302)
        except requests.RequestException as exc:
            logger.error("Jenkins cancel failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # verify_webhook
    # ------------------------------------------------------------------

    def verify_webhook(self, request) -> bool:
        """Jenkins webhooks typically use token-based auth or are unauthenticated.

        If ci_token is configured, compare with X-Jenkins-Token header.
        """
        expected = self.token
        if not expected:
            # No token configured — accept (caller should add their own layer)
            return True
        provided = request.headers.get("X-Jenkins-Token", "").strip()
        import hmac
        return hmac.compare_digest(provided, expected)

    # ------------------------------------------------------------------
    # ping
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        """Check Jenkins connectivity via GET {base_url}/api/json."""
        session = self._get_session()
        url = self.base_url.rstrip("/") + "/api/json"
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "detail": f"Jenkins {data.get('nodeName', 'unknown')}"}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)[:200]}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _job_url(self) -> str:
        """Classic API base for the configured job."""
        # Jenkins classic URL: {base}/job/{job_name}
        parts = [self.base_url, "job"] + self.job_name.split("/")
        return "/".join(p.strip("/") for p in parts if p)

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        s = requests.Session()
        s.verify = self.verify_ssl
        s.headers.update(self._headers())
        if self.token:
            # Jenkins supports Basic auth with user:token
            s.auth = ("", self.token)
        # Retry on transient errors
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        self._session = s
        return s

    def _poll_queue(self, session: requests.Session, queue_url: str) -> Optional[str]:
        """Poll queue item until executable build appears. Returns build URL or None."""
        deadline = time.time() + _QUEUE_POLL_MAX_SEC
        api_url = queue_url + "api/json"
        while time.time() < deadline:
            try:
                resp = session.get(api_url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                executable = data.get("executable")
                if executable:
                    return executable.get("url", "")
                if data.get("cancelled"):
                    return None
            except (requests.RequestException, ValueError):
                pass
            time.sleep(_QUEUE_POLL_INTERVAL_SEC)
        logger.warning("Queue poll timed out for %s", queue_url)
        return None

    def _parse_blue_ocean_status(self, data: dict, run) -> CiRunStatus:
        state = data.get("state", "UNKNOWN")
        result = data.get("result", "UNKNOWN")
        # Prefer result for terminal, state for running
        raw_status = result if result != "UNKNOWN" else state
        status = jenkins_to_canonical(raw_status)
        return CiRunStatus(
            status=status,
            external_run_id=run.external_run_id,
            external_url=run.external_url or data.get("_links", {}).get("self", {}).get("href", ""),
            duration_ms=data.get("durationInMillis"),
        )

    def _parse_classic_status(self, data: dict, run) -> CiRunStatus:
        building = data.get("building", False)
        result = data.get("result")
        if building:
            raw_status = "RUNNING"
        elif result:
            raw_status = result
        else:
            raw_status = "QUEUED"
        status = jenkins_to_canonical(raw_status)
        return CiRunStatus(
            status=status,
            external_run_id=run.external_run_id,
            external_url=run.external_url or data.get("url", ""),
            duration_ms=data.get("duration"),
        )

    def _parse_blue_ocean_nodes(self, nodes_data: list) -> List[CiJobResult]:
        jobs = []
        for node in nodes_data:
            jobs.append(CiJobResult(
                name=node.get("displayName", node.get("id", "")),
                stage=node.get("type", ""),
                status=jenkins_to_canonical(
                    node.get("result") or node.get("state", "UNKNOWN")
                ),
                duration_ms=node.get("durationInMillis"),
                external_job_id=node.get("id"),
                external_url=node.get("_links", {}).get("self", {}).get("href", ""),
            ))
        return jobs
