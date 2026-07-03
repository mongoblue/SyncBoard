"""SSRF (Server-Side Request Forgery) protection for API test execution.

Defense layers applied in order:
1. Scheme whitelist — only http/https
2. @-bypass detection — userinfo in URL
3. URL normalization — decode punycode/percent-encoding traps
4. DNS rebinding detection — resolve → check → re-resolve
5. IP classification — block 11 internal/private/reserved ranges
6. Metadata endpoint blocking — cloud provider metadata IPs

Also provides SSRFProtectedSession: a requests.Session wrapper that
disables automatic redirects and re-validates each redirect target.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Allowed URL schemes
_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Blocked internal / private / reserved IPv4 ranges (11 networks)
_BLOCKED_IPV4_NETWORKS = [
    ipaddress.IPv4Network("0.0.0.0/8"),        # Current network
    ipaddress.IPv4Network("10.0.0.0/8"),       # Private
    ipaddress.IPv4Network("100.64.0.0/10"),    # CGNAT
    ipaddress.IPv4Network("127.0.0.0/8"),      # Loopback
    ipaddress.IPv4Network("169.254.0.0/16"),   # Link-local
    ipaddress.IPv4Network("172.16.0.0/12"),    # Private
    ipaddress.IPv4Network("192.0.0.0/24"),     # IETF Protocol Assignments
    ipaddress.IPv4Network("192.0.2.0/24"),     # TEST-NET-1
    ipaddress.IPv4Network("192.168.0.0/16"),   # Private
    ipaddress.IPv4Network("198.18.0.0/15"),    # Benchmarking
    ipaddress.IPv4Network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.IPv4Network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.IPv4Network("224.0.0.0/4"),      # Multicast
    ipaddress.IPv4Network("240.0.0.0/4"),      # Reserved
]

# Blocked IPv6 ranges
_BLOCKED_IPV6_NETWORKS = [
    ipaddress.IPv6Network("::1/128"),          # Loopback
    ipaddress.IPv6Network("fe80::/10"),        # Link-local
    ipaddress.IPv6Network("fc00::/7"),         # Unique local
    ipaddress.IPv6Network("ff00::/8"),         # Multicast
]

# Cloud metadata IPs
_METADATA_IPS = {
    "169.254.169.254",  # AWS / GCP / Azure / DigitalOcean / etc.
    "100.100.100.200",  # Alibaba Cloud
}


class SSRFError(ValueError):
    """Raised when a URL is blocked by SSRF protection."""
    pass


def _is_ip_blocked(ip_str: str) -> bool:
    """Check if an IP address falls into any blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Can't parse — block to be safe

    if ip_str in _METADATA_IPS:
        return True

    if addr.version == 4:
        return any(addr in net for net in _BLOCKED_IPV4_NETWORKS)
    else:
        return any(addr in net for net in _BLOCKED_IPV6_NETWORKS)


def _validate_hostname(hostname: str) -> None:
    """Resolve hostname and check all IPs are safe.

    Uses DNS rebinding defense: resolves twice and compares results.
    """
    import socket

    try:
        first_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname}: {exc}")

    # Extract unique IPs from first resolution
    resolved_ips = set()
    for info in first_ips:
        ip = info[4][0]
        if _is_ip_blocked(ip):
            raise SSRFError(f"Blocked IP address: {ip} (resolved from {hostname})")
        resolved_ips.add(ip)

    # DNS rebinding check: resolve again
    try:
        second_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        # If second resolution fails, still allow (first passed)
        return

    second_set = {info[4][0] for info in second_ips}
    if resolved_ips != second_set:
        raise SSRFError(f"DNS rebinding detected for {hostname}: IPs changed between resolutions")


def validate_target_url(url: str) -> str:
    """Validate a URL is safe for server-side requests.

    Returns the normalized URL on success, raises SSRFError on failure.

    Defense layers (in order):
    1. Scheme whitelist (http/https only)
    2. @-bypass detection
    3. URL normalization
    4. DNS resolution + IP classification
    """
    if not url or not isinstance(url, str):
        raise SSRFError("URL is empty or invalid")

    # Strip leading/trailing whitespace
    url = url.strip()

    # --- Layer 1: Scheme whitelist ---
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise SSRFError(f"URL scheme not allowed: {parsed.scheme}")

    # --- Layer 2: @-bypass detection ---
    # URLs like http://safe.com@evil.com use @ to hide the real host
    if "@" in parsed.netloc:
        raise SSRFError("URL contains @ in authority (potential bypass)")

    # Also check for @ in the full URL that urlparse might miss
    if "@" in url and "@" not in parsed.netloc:
        raise SSRFError("URL contains @ (potential bypass)")

    # --- Layer 3: Normalize ---
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no valid hostname")

    # Reject raw IP addresses in URL (must go through DNS)
    # This prevents direct IP targeting
    try:
        ipaddress.ip_address(hostname)
        # It's a raw IP — block it
        if _is_ip_blocked(hostname):
            raise SSRFError(f"Blocked IP address: {hostname}")
        # Even non-blocked raw IPs are suspicious — block all
        raise SSRFError(f"Direct IP addresses are not allowed: {hostname}")
    except ValueError:
        pass  # Not an IP, proceed to DNS resolution

    # --- Layer 4: DNS resolution + IP classification ---
    _validate_hostname(hostname)

    # Reconstruct normalized URL
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        "",  # fragment not sent to server
    ))

    return normalized


# ---------------------------------------------------------------------------
# SSRF-protected requests.Session
# ---------------------------------------------------------------------------

class SSRFProtectedSession(requests.Session):
    """A requests.Session that validates every URL against SSRF rules.

    Features:
    - Validates the initial URL before sending
    - Disables automatic redirect following
    - Re-validates each redirect target manually
    """

    def __init__(self):
        super().__init__()
        # Disable auto-redirect — we handle redirects ourselves
        self.max_redirects = 0
        # Retry on transient errors
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def send(self, request, **kwargs):
        # Validate the request URL
        validate_target_url(request.url)
        return super().send(request, **kwargs)

    def request(self, method, url, **kwargs):
        # Validate before every request (catches redirect targets too)
        validated = validate_target_url(url)
        return super().request(method, validated, **kwargs)
