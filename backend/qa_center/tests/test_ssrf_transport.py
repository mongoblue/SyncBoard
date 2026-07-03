from __future__ import annotations

from dataclasses import dataclass

import pytest

from qa_center import api_execution


@dataclass
class FakeHttpResponse:
    status_code: int
    headers: dict
    cookies: dict
    content: bytes
    text: str
    elapsed_ms: int
    url: str


class FakeHttpClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def send(self, *, method, url, headers, params, body, body_mode, cookies, auth, timeout, allow_redirects):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "body": body,
                "body_mode": body_mode,
                "cookies": cookies,
                "auth": auth,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
        )
        if not self.responses:
            return FakeHttpResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                content=b"{}",
                text="{}",
                elapsed_ms=10,
                url=url,
            )
        return self.responses.pop(0)


def _make_request(url: str, *, allow_redirects=False) -> api_execution.ApiPreparedRequest:
    return api_execution.ApiPreparedRequest(
        method="GET",
        rendered_url=url,
        headers={},
        query_params=None,
        body=None,
        body_mode="none",
        files=None,
        cookies=None,
        auth=None,
        timeout=30,
        allow_redirects=allow_redirects,
        trace_id="trace-ssrf",
        metadata={},
    )


def _make_context(**policies) -> api_execution.ApiExecutionContext:
    return api_execution.ApiExecutionContext(
        trace_id="trace-ssrf",
        project_id="project-1",
        environment_id="env-1",
        system_vars={},
        global_vars={},
        environment_vars={},
        run_overrides={},
        chain_vars={},
        locked_variables=set(),
        secret_names=set(),
        secret_values=set(),
        policies=policies,
        runtime_mode="real",
        metadata={},
    )


def test_ssrf_transport_blocks_metadata_even_if_allowlisted():
    request = _make_request("http://169.254.169.254/latest/meta-data")
    context = _make_context(
        allowed_hosts=["169.254.169.254"],
        allowed_cidrs=["10.0.0.0/8"],
    )
    client = FakeHttpClient()
    transport = api_execution.SSRFProtectedRequestsTransport(http_client=client)

    response = transport.send(request, context)

    assert response.error_type == "ssrf_blocked"
    assert client.calls == []


def test_ssrf_transport_allows_exact_allowlisted_private_hostname(monkeypatch):
    request = _make_request("http://internal.example.com/api/users")
    context = _make_context(allowed_hosts=["internal.example.com"], allowed_cidrs=[])
    client = FakeHttpClient()
    transport = api_execution.SSRFProtectedRequestsTransport(http_client=client)

    monkeypatch.setattr(
        "qa_center.api_execution.transport._resolve_hostname_twice",
        lambda hostname: ({"10.0.0.42"}, {"10.0.0.42"}),
    )

    response = transport.send(request, context)

    assert response.error_type is None
    assert len(client.calls) == 1
    assert client.calls[0]["url"] == "http://internal.example.com/api/users"


def test_ssrf_transport_allowlist_does_not_skip_dns_rebinding_detection(monkeypatch):
    request = _make_request("http://internal.example.com/api/users")
    context = _make_context(allowed_hosts=["internal.example.com"], allowed_cidrs=[])
    client = FakeHttpClient()
    transport = api_execution.SSRFProtectedRequestsTransport(http_client=client)

    monkeypatch.setattr(
        "qa_center.api_execution.transport._resolve_hostname_twice",
        lambda hostname: ({"10.0.0.42"}, {"10.0.0.43"}),
    )

    response = transport.send(request, context)

    assert response.error_type == "ssrf_blocked"
    assert client.calls == []


def test_ssrf_transport_redirect_revalidates_each_target(monkeypatch):
    request = _make_request("http://public.example.com/start", allow_redirects=True)
    context = _make_context(allowed_hosts=["internal.example.com"], allowed_cidrs=[])
    client = FakeHttpClient(
        [
            FakeHttpResponse(
                status_code=302,
                headers={"Location": "http://internal.example.com/next"},
                cookies={},
                content=b"",
                text="",
                elapsed_ms=10,
                url="http://public.example.com/start",
            ),
            FakeHttpResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                content=b'{"ok": true}',
                text='{"ok": true}',
                elapsed_ms=10,
                url="http://internal.example.com/next",
            ),
        ]
    )
    transport = api_execution.SSRFProtectedRequestsTransport(http_client=client)

    def fake_resolve(hostname):
        if hostname == "public.example.com":
            return {"8.8.8.8"}, {"8.8.8.8"}
        if hostname == "internal.example.com":
            return {"10.0.0.42"}, {"10.0.0.42"}
        raise AssertionError(f"unexpected hostname {hostname}")

    monkeypatch.setattr("qa_center.api_execution.transport._resolve_hostname_twice", fake_resolve)

    response = transport.send(request, context)

    assert response.error_type is None
    assert len(client.calls) == 2
    assert response.final_url == "http://internal.example.com/next"
    assert response.redirect_chain == [
        {
            "status_code": 302,
            "location": "http://internal.example.com/next",
            "url": "http://public.example.com/start",
        }
    ]


def test_ssrf_transport_redirect_block_returns_ssrf_blocked(monkeypatch):
    request = _make_request("http://public.example.com/start", allow_redirects=True)
    context = _make_context(allowed_hosts=[], allowed_cidrs=[])
    client = FakeHttpClient(
        [
            FakeHttpResponse(
                status_code=302,
                headers={"Location": "http://127.0.0.1/private"},
                cookies={},
                content=b"",
                text="",
                elapsed_ms=10,
                url="http://public.example.com/start",
            ),
        ]
    )
    transport = api_execution.SSRFProtectedRequestsTransport(http_client=client)

    monkeypatch.setattr(
        "qa_center.api_execution.transport._resolve_hostname_twice",
        lambda hostname: ({"8.8.8.8"}, {"8.8.8.8"}),
    )

    response = transport.send(request, context)

    assert response.error_type == "ssrf_blocked"
    assert len(client.calls) == 1


def test_runtime_guard_choose_default_transport_for_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    guard = api_execution.RuntimeGuard()

    assert guard.choose_default_transport() == "ssrf_protected_requests_transport"


def test_requests_transport_uses_http_client_without_ssrf_validation():
    request = _make_request("http://public.example.com/api/users")
    context = _make_context()
    client = FakeHttpClient(
        [
            FakeHttpResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                cookies={},
                content=b'{"ok": true}',
                text='{"ok": true}',
                elapsed_ms=9,
                url="http://public.example.com/api/users",
            )
        ]
    )
    transport = api_execution.RequestsTransport(http_client=client)

    response = transport.send(request, context)

    assert response.error_type is None
    assert len(client.calls) == 1
    assert response.status_code == 200
