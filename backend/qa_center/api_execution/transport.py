from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass, field
from typing import List, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

from .contracts import ApiExecutionContext, ApiPreparedRequest, ApiTransport, TransportResponse


ALLOWED_SCHEMES = {"http", "https"}
METADATA_IPS = {"169.254.169.254", "100.100.100.200"}
PRIVATE_IPV4_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]
LOOPBACK_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]
LINK_LOCAL_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
]
MULTICAST_RESERVED_NETWORKS = [
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("fc00::/7"),
]


def _resolve_hostname_twice(hostname: str) -> tuple[set[str], set[str]]:
    first = {
        info[4][0]
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    }
    second = {
        info[4][0]
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    }
    return first, second


def _normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def _ip_matches_allowed_cidrs(ip_str: str, allowed_cidrs: list[str]) -> bool:
    addr = ipaddress.ip_address(ip_str)
    return any(
        addr.version == ipaddress.ip_network(cidr).version and addr in ipaddress.ip_network(cidr)
        for cidr in allowed_cidrs
    )


def _is_in_networks(ip_str: str, networks: list[ipaddress._BaseNetwork]) -> bool:
    addr = ipaddress.ip_address(ip_str)
    return any(addr.version == network.version and addr in network for network in networks)


def _classify_ip(
    ip_str: str,
    *,
    allowed_cidrs: list[str],
    allow_private: bool,
) -> None:
    if ip_str in METADATA_IPS:
        raise ValueError(f"metadata endpoint is always blocked: {ip_str}")
    if _is_in_networks(ip_str, LOOPBACK_NETWORKS):
        raise ValueError(f"loopback address is blocked: {ip_str}")
    if _is_in_networks(ip_str, LINK_LOCAL_NETWORKS):
        raise ValueError(f"link-local address is blocked: {ip_str}")
    if _is_in_networks(ip_str, MULTICAST_RESERVED_NETWORKS):
        raise ValueError(f"reserved address is blocked: {ip_str}")
    if _is_in_networks(ip_str, PRIVATE_IPV4_NETWORKS):
        if allow_private:
            return
        if allowed_cidrs and _ip_matches_allowed_cidrs(ip_str, allowed_cidrs):
            return
        raise ValueError(f"private address is blocked: {ip_str}")


class _RequestsHttpClient:
    def __init__(self) -> None:
        import requests

        self.session = requests.Session()

    def send(
        self,
        *,
        method,
        url,
        headers,
        params,
        body,
        body_mode,
        cookies,
        auth,
        timeout,
        allow_redirects,
    ):
        if cookies:
            self.session.cookies.update(cookies)

        kwargs = {
            "headers": headers,
            "params": params,
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        }
        if body_mode == "json":
            kwargs["json"] = body
        elif body_mode in {"raw", "form"}:
            kwargs["data"] = body
        response = self.session.request(method=method, url=url, **kwargs)
        return type(
            "HttpResponse",
            (),
            {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "cookies": dict(response.cookies),
                "content": response.content,
                "text": response.text,
                "elapsed_ms": int(response.elapsed.total_seconds() * 1000),
                "url": response.url,
            },
        )()


@dataclass
class MockTransport(ApiTransport):
    responses: Sequence[TransportResponse] = field(default_factory=list)
    sent_requests: List[ApiPreparedRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._queue = list(self.responses)

    def send(
        self,
        request: ApiPreparedRequest,
        context: ApiExecutionContext,
    ) -> TransportResponse:
        self.sent_requests.append(request)
        if self._queue:
            return self._queue.pop(0)
        return TransportResponse(
            status_code=200,
            headers={},
            cookies={},
            body_bytes=b"",
            text="",
            elapsed_ms=0,
            final_url=request.rendered_url,
            redirect_chain=[],
        )


class RequestsTransport(ApiTransport):
    def __init__(self, *, http_client=None) -> None:
        self.http_client = http_client or _RequestsHttpClient()

    def send(
        self,
        request: ApiPreparedRequest,
        context: ApiExecutionContext,
    ) -> TransportResponse:
        response = self.http_client.send(
            method=request.method,
            url=request.rendered_url,
            headers=request.headers,
            params=request.query_params,
            body=request.body,
            body_mode=request.body_mode,
            cookies=request.cookies,
            auth=request.auth,
            timeout=request.timeout,
            allow_redirects=request.allow_redirects,
        )
        return TransportResponse(
            status_code=response.status_code,
            headers=response.headers,
            cookies=response.cookies,
            body_bytes=response.content,
            text=response.text,
            elapsed_ms=response.elapsed_ms,
            final_url=response.url,
            redirect_chain=[],
        )


class SSRFProtectedRequestsTransport(ApiTransport):
    def __init__(self, *, http_client=None) -> None:
        self.http_client = http_client or _RequestsHttpClient()

    def send(
        self,
        request: ApiPreparedRequest,
        context: ApiExecutionContext,
    ) -> TransportResponse:
        try:
            return self._send_with_validation(request, context)
        except Exception as exc:
            return TransportResponse(
                status_code=0,
                headers={},
                cookies={},
                body_bytes=b"",
                text="",
                elapsed_ms=0,
                final_url=request.rendered_url,
                redirect_chain=[],
                error_type="ssrf_blocked",
                error_message=str(exc),
            )

    def _send_with_validation(
        self,
        request: ApiPreparedRequest,
        context: ApiExecutionContext,
    ) -> TransportResponse:
        redirect_chain: list[dict] = []
        current_url = _normalize_url(request.rendered_url)
        allowlist_hosts = [
            str(host).lower() for host in (context.policies.get("allowed_hosts") or [])
        ]
        allowlist_cidrs = list(context.policies.get("allowed_cidrs") or [])

        while True:
            self._validate_target_url(
                current_url,
                allowed_hosts=allowlist_hosts,
                allowed_cidrs=allowlist_cidrs,
                app_env=context.policies.get("app_env", ""),
            )

            response = self.http_client.send(
                method=request.method,
                url=current_url,
                headers=request.headers,
                params=request.query_params,
                body=request.body,
                body_mode=request.body_mode,
                cookies=request.cookies,
                auth=request.auth,
                timeout=request.timeout,
                allow_redirects=False,
            )

            if not request.allow_redirects or response.status_code not in {301, 302, 303, 307, 308}:
                return TransportResponse(
                    status_code=response.status_code,
                    headers=response.headers,
                    cookies=response.cookies,
                    body_bytes=response.content,
                    text=response.text,
                    elapsed_ms=response.elapsed_ms,
                    final_url=response.url,
                    redirect_chain=redirect_chain,
                )

            location = response.headers.get("Location") or response.headers.get("location")
            if not location:
                return TransportResponse(
                    status_code=response.status_code,
                    headers=response.headers,
                    cookies=response.cookies,
                    body_bytes=response.content,
                    text=response.text,
                    elapsed_ms=response.elapsed_ms,
                    final_url=response.url,
                    redirect_chain=redirect_chain,
                )

            redirect_chain.append(
                {
                    "status_code": response.status_code,
                    "location": location,
                    "url": response.url,
                }
            )
            current_url = _normalize_url(urljoin(response.url, location))

    def _validate_target_url(
        self,
        url: str,
        *,
        allowed_hosts: list[str],
        allowed_cidrs: list[str],
        app_env: str,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            raise ValueError(f"scheme not allowed: {parsed.scheme}")
        if "@" in parsed.netloc or "@" in url:
            raise ValueError("authority contains @")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("hostname missing")

        lower_host = hostname.lower()
        if app_env in {"staging", "production"} and lower_host == "localhost":
            raise ValueError("localhost is blocked in strict environments")

        try:
            ipaddress.ip_address(lower_host)
        except ValueError:
            first, second = _resolve_hostname_twice(lower_host)
            if first != second:
                raise ValueError(f"DNS rebinding detected for {lower_host}")
            allow_private = lower_host in allowed_hosts
            for resolved_ip in first:
                _classify_ip(
                    resolved_ip,
                    allowed_cidrs=allowed_cidrs,
                    allow_private=allow_private,
                )
        else:
            _classify_ip(
                lower_host,
                allowed_cidrs=allowed_cidrs,
                allow_private=False,
            )


class DjangoTestClientTransport(ApiTransport):
    def __init__(self, *, user=None) -> None:
        self.user = user

    def send(
        self,
        request: ApiPreparedRequest,
        context: ApiExecutionContext,
    ) -> TransportResponse:
        from django.test import Client

        client = Client()
        if self.user is not None:
            client.force_login(self.user)
        if request.cookies:
            for key, value in request.cookies.items():
                client.cookies[key] = value

        path = request.rendered_url
        if request.query_params:
            from urllib.parse import urlencode

            path = f"{path}?{urlencode(request.query_params, doseq=True)}"

        headers = request.headers or {}
        content_type = headers.get("Content-Type") or headers.get("content-type")
        data = None
        if request.body_mode == "json" and request.body is not None:
            data = json.dumps(request.body, ensure_ascii=False)
            content_type = content_type or "application/json"
        elif request.body_mode in {"raw", "form"}:
            data = request.body
            content_type = content_type or "application/json"

        response = client.generic(
            request.method.upper(),
            path,
            data=data,
            content_type=content_type,
            headers=headers,
        )
        return TransportResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            cookies=dict(client.cookies),
            body_bytes=response.content,
            text=response.content.decode("utf-8", errors="replace"),
            elapsed_ms=0,
            final_url=path,
            redirect_chain=[],
        )
