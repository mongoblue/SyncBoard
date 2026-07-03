"""
TargetProbeService — 目标 URL 预检服务。

在启动 Locust 压力测试前，对目标 URL 执行全面的连通性和安全性检查：
    - URL scheme 校验（仅允许 http/https）
    - DNS 解析 + IP 分类（localhost / 内网 / 公网 / 云 metadata）
    - TCP 端口连通性
    - HTTP HEAD/GET 请求
    - TLS 证书校验
    - SSRF 策略拦截

用法::

    from qa_center.execution.probe import TargetProbeService, ProbeResult

    service = TargetProbeService()
    result = service.probe("https://example.com/api/health", method="GET")
    if not result.ok:
        raise WorkerError(result.error_summary, LifecycleState.ERROR, result.failure_reason)
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ── SSRF 黑名单（禁止压测的目标） ──────────────────────────────

_SSRF_BLOCKED_HOSTS: Tuple[str, ...] = (
    '169.254.169.254',                # AWS / GCP / Azure metadata
    'metadata.google.internal',       # GCP metadata
    'metadata',                       # generic cloud metadata
    '100.100.100.200',               # Alibaba Cloud metadata
    '169.254.0.23',                   # Azure instance metadata
    '169.254.0.2',                    # Azure wire server
    '169.254.1.1',                    # DigitalOcean metadata
)

_SSRF_BLOCKED_CIDRS: Tuple[str, ...] = (
    '169.254.0.0/16',                # Link-local / cloud metadata
    '100.64.0.0/10',                 # Carrier-grade NAT (used by some clouds)
)

# 默认允许的内网 CIDR（当 PERF_BLOCK_PRIVATE_CIDRS=True 时生效）
_PRIVATE_CIDRS: Tuple[str, ...] = (
    '10.0.0.0/8',
    '172.16.0.0/12',
    '192.168.0.0/16',
    '127.0.0.0/8',
    '0.0.0.0/8',
    '::1/128',
    'fc00::/7',
    'fe80::/10',
)


# ── 配置辅助 ──────────────────────────────────────────────────


def _get_conf(name: str, default: Any) -> Any:
    """从 Django settings 读取配置，不存在时使用默认值。"""
    return getattr(settings, name, default)


# ── ProbeResult ────────────────────────────────────────────────


@dataclass
class ProbeResult:
    """URL 预检的完整结果。"""

    # ── 输入 ──────────────────────────────────────────────────
    url: str = ""
    method: str = "GET"
    probe_timeout: float = 5.0

    # ── 总体结果 ──────────────────────────────────────────────
    ok: bool = False
    failure_reason: str = ""          # probe_failed / probe_timeout / blocked_by_policy / invalid_scheme
    error_summary: str = ""

    # ── URL 解析 ──────────────────────────────────────────────
    scheme: str = ""
    hostname: str = ""
    port: int = 443
    path: str = "/"

    # ── Scheme 校验 ────────────────────────────────────────────
    scheme_allowed: bool = True
    scheme_block_reason: str = ""

    # ── DNS 解析 ──────────────────────────────────────────────
    dns_resolved: bool = False
    dns_error: str = ""
    resolved_ips: List[str] = field(default_factory=list)

    # ── IP 分类 ────────────────────────────────────────────────
    is_localhost: bool = False
    is_private: bool = False
    is_link_local: bool = False
    is_cloud_metadata: bool = False
    ip_classification_notes: List[str] = field(default_factory=list)

    # ── 策略检查 ──────────────────────────────────────────────
    blocked_by_policy: bool = False
    policy_block_reason: str = ""
    localhost_allowed: bool = False
    private_cidr_blocked: bool = False

    # ── TCP 连通性 ────────────────────────────────────────────
    tcp_connect_ok: bool = False
    tcp_connect_error: str = ""
    tcp_connect_ms: float = 0

    # ── HTTP 请求 ──────────────────────────────────────────────
    http_ok: bool = False
    http_status_code: Optional[int] = None
    http_error: str = ""
    http_duration_ms: float = 0

    # ── TLS ────────────────────────────────────────────────────
    tls_ok: bool = False
    tls_error: str = ""
    tls_version: str = ""
    tls_cert_subject: str = ""
    tls_cert_expires: str = ""

    # ── 时间戳 ────────────────────────────────────────────────
    started_at: float = 0
    finished_at: float = 0
    total_duration_ms: float = 0

    @property
    def elapsed_ms(self) -> float:
        return round(self.total_duration_ms, 1) if self.total_duration_ms else 0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为前端可用的 dict。"""
        return {
            'ok': self.ok,
            'failure_reason': self.failure_reason,
            'error_summary': self.error_summary,
            'url': self.url,
            'method': self.method,
            'scheme': self.scheme,
            'hostname': self.hostname,
            'port': self.port,
            'path': self.path,
            'scheme_allowed': self.scheme_allowed,
            'scheme_block_reason': self.scheme_block_reason,
            'dns_resolved': self.dns_resolved,
            'dns_error': self.dns_error,
            'resolved_ips': self.resolved_ips,
            'is_localhost': self.is_localhost,
            'is_private': self.is_private,
            'is_link_local': self.is_link_local,
            'is_cloud_metadata': self.is_cloud_metadata,
            'ip_classification_notes': self.ip_classification_notes,
            'blocked_by_policy': self.blocked_by_policy,
            'policy_block_reason': self.policy_block_reason,
            'localhost_allowed': self.localhost_allowed,
            'private_cidr_blocked': self.private_cidr_blocked,
            'tcp_connect_ok': self.tcp_connect_ok,
            'tcp_connect_error': self.tcp_connect_error,
            'tcp_connect_ms': self.tcp_connect_ms,
            'http_ok': self.http_ok,
            'http_status_code': self.http_status_code,
            'http_error': self.http_error,
            'http_duration_ms': self.http_duration_ms,
            'tls_ok': self.tls_ok,
            'tls_error': self.tls_error,
            'tls_version': self.tls_version,
            'tls_cert_subject': self.tls_cert_subject,
            'total_duration_ms': self.total_duration_ms,
        }

    @property
    def is_localhost_warning(self) -> bool:
        """是否需要显示 localhost 警告。"""
        return self.is_localhost and self.localhost_allowed


# ── TargetProbeService ─────────────────────────────────────────


class TargetProbeService:
    """目标 URL 预检服务。

    在真正启动 Locust 压测前，从执行器所在环境主动检查目标 URL 的
    连通性和安全性。预检失败时不会启动 Locust，直接进入 error 状态。
    """

    def __init__(self):
        self._result: Optional[ProbeResult] = None

    # ── 公共入口 ────────────────────────────────────────────────

    def probe(
        self,
        url: str,
        method: str = "GET",
        timeout: Optional[float] = None,
    ) -> ProbeResult:
        """执行完整的 URL 预检。

        Args:
            url: 目标 URL（完整 URL，含 scheme）
            method: HTTP 方法
            timeout: 超时秒数，默认从 settings.PERF_PROBE_TIMEOUT_SECONDS 读取

        Returns:
            ProbeResult 包含所有检查结果
        """
        if timeout is None:
            timeout = _get_conf('PERF_PROBE_TIMEOUT_SECONDS', 5.0)

        self._result = ProbeResult(
            url=url,
            method=method,
            probe_timeout=timeout,
        )
        self._result.started_at = time.time()

        try:
            # 1. 解析 URL + scheme 校验
            if not self._check_scheme():
                return self._finish()

            # 2. 策略检查（SSRF 拦截 + localhost/内网策略）
            if not self._check_policy():
                return self._finish()

            # 3. DNS 解析
            if not self._check_dns():
                return self._finish()

            # 4. IP 分类（可能触发 localhost/内网策略拦截）
            self._classify_ips()

            # 策略拦截检查（在 DNS 解析后，因为需要 IP 分类）
            if self._result.blocked_by_policy:
                return self._finish()

            # 5. TCP 连通性
            self._check_tcp()

            # 6. HTTP 请求 + TLS
            self._check_http()

        except Exception as exc:
            logger.exception("TargetProbeService 内部异常: %s", exc)
            self._result.failure_reason = 'probe_error'
            self._result.error_summary = f'预检内部异常: {exc}'

        return self._finish()

    def _finish(self) -> ProbeResult:
        """设置结束时间并返回结果。"""
        if self._result is None:
            return ProbeResult(url='', failure_reason='probe_error')
        self._result.finished_at = time.time()
        self._result.total_duration_ms = round(
            (self._result.finished_at - self._result.started_at) * 1000, 1
        )
        self._result.ok = (
            self._result.scheme_allowed
            and not self._result.blocked_by_policy
            and self._result.dns_resolved
            and self._result.http_ok
        )
        if not self._result.ok and not self._result.failure_reason:
            if not self._result.scheme_allowed:
                self._result.failure_reason = 'invalid_scheme'
            elif self._result.blocked_by_policy:
                self._result.failure_reason = 'blocked_by_policy'
            elif not self._result.dns_resolved:
                self._result.failure_reason = 'probe_failed'
            elif self._result.http_error:
                self._result.failure_reason = 'probe_failed'
            else:
                self._result.failure_reason = 'probe_failed'
        return self._result

    # ── 1. URL Scheme 校验 ─────────────────────────────────────

    def _check_scheme(self) -> bool:
        """仅允许 http/https scheme。"""
        r = self._result
        try:
            parsed = urlparse(r.url)
        except Exception as exc:
            r.scheme_allowed = False
            r.scheme_block_reason = f'URL 解析失败: {exc}'
            r.error_summary = f'URL 格式无效: {r.url}'
            return False

        r.scheme = parsed.scheme.lower()
        r.hostname = parsed.hostname or ''
        r.path = parsed.path or '/'
        if parsed.query:
            r.path += '?' + parsed.query

        if parsed.port:
            r.port = parsed.port
        elif r.scheme == 'https':
            r.port = 443
        elif r.scheme == 'http':
            r.port = 80

        # ── 禁止非 http/https ──────────────────────────────────
        blocked_schemes = _get_conf('PERF_BLOCKED_SCHEMES', (
            'file', 'ftp', 'gopher', 'javascript', 'data', 'vbscript',
        ))

        if r.scheme in blocked_schemes:
            r.scheme_allowed = False
            r.scheme_block_reason = f'Scheme "{r.scheme}" 不允许用于压力测试'
            r.error_summary = r.scheme_block_reason
            logger.warning("Probe blocked: %s → scheme=%s", r.url, r.scheme)
            return False

        if r.scheme not in ('http', 'https'):
            r.scheme_allowed = False
            r.scheme_block_reason = f'Scheme "{r.scheme}" 不支持（仅允许 http/https）'
            r.error_summary = r.scheme_block_reason
            logger.warning("Probe blocked: %s → unsupported scheme=%s", r.url, r.scheme)
            return False

        if not r.hostname:
            r.scheme_allowed = False
            r.scheme_block_reason = '无法从 URL 中提取 hostname'
            r.error_summary = r.scheme_block_reason
            return False

        return True

    # ── 2. 策略检查 ─────────────────────────────────────────────

    def _check_policy(self) -> bool:
        """检查 SSRF 策略、localhost/内网规则。"""
        r = self._result
        hostname_lower = r.hostname.lower()

        # ── 检查云 metadata 服务地址 ────────────────────────────
        blocked_hosts = _get_conf('PERF_BLOCKED_HOSTS', _SSRF_BLOCKED_HOSTS)
        for blocked in blocked_hosts:
            if hostname_lower == blocked.lower():
                r.blocked_by_policy = True
                r.policy_block_reason = (
                    f'目标 "{r.hostname}" 为云 metadata 服务地址，'
                    f'禁止压力测试（SSRF 保护）'
                )
                r.error_summary = r.policy_block_reason
                r.is_cloud_metadata = True
                logger.warning("Probe BLOCKED by policy: %s (metadata)", r.url)
                return False

        return True

    # ── 3. DNS 解析 ────────────────────────────────────────────

    def _check_dns(self) -> bool:
        """DNS 解析目标 hostname。"""
        r = self._result
        try:
            addrinfo = socket.getaddrinfo(
                r.hostname, r.port,
                socket.AF_UNSPEC, socket.SOCK_STREAM,
            )
            ips_seen: set = set()
            for family, _, _, _, sockaddr in addrinfo:
                ip = sockaddr[0]
                if ip not in ips_seen:
                    ips_seen.add(ip)
                    r.resolved_ips.append(ip)
            r.dns_resolved = True
            logger.info("Probe DNS: %s → %s", r.hostname, r.resolved_ips)
            return True

        except socket.gaierror as exc:
            r.dns_error = str(exc)
            r.error_summary = f'DNS 解析失败: {r.hostname} — {exc}'
            logger.warning("Probe DNS failed: %s → %s", r.hostname, exc)
            return False
        except Exception as exc:
            r.dns_error = str(exc)
            r.error_summary = f'DNS 解析异常: {r.hostname} — {exc}'
            return False

    # ── 4. IP 分类 ──────────────────────────────────────────────

    def _classify_ips(self) -> None:
        """对解析到的 IP 进行分类。"""
        r = self._result

        for ip_str in r.resolved_ips:
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            if ip.is_loopback:
                r.is_localhost = True
                r.ip_classification_notes.append(f'{ip_str}: localhost/loopback')
            elif ip.is_link_local:
                r.is_link_local = True
                r.ip_classification_notes.append(f'{ip_str}: link-local (169.254.x.x)')
            elif ip.is_private:
                r.is_private = True
                r.ip_classification_notes.append(f'{ip_str}: 内网地址')
            else:
                r.ip_classification_notes.append(f'{ip_str}: 公网地址')

        # ── CIDR 检查 ─────────────────────────────────────────
        blocked_cidrs = _get_conf('PERF_BLOCKED_CIDRS', _SSRF_BLOCKED_CIDRS)
        for ip_str in r.resolved_ips:
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            for cidr_str in blocked_cidrs:
                if ip in ipaddress.ip_network(cidr_str):
                    r.is_cloud_metadata = True
                    r.ip_classification_notes.append(f'{ip_str}: 匹配 SSRF 阻断 CIDR {cidr_str}')

        # ── 内网策略 ──────────────────────────────────────────
        r.localhost_allowed = _get_conf('PERF_ALLOW_LOCALHOST', False)
        r.private_cidr_blocked = _get_conf('PERF_BLOCK_PRIVATE_CIDRS', True)

        if r.is_localhost and not r.localhost_allowed:
            r.blocked_by_policy = True
            r.policy_block_reason = (
                f'目标地址解析为 localhost ({r.resolved_ips})，'
                f'但 PERF_ALLOW_LOCALHOST=False。'
                f'生产环境通常不允许对 localhost 发起压测。'
            )
            r.error_summary = r.policy_block_reason
            logger.warning("Probe BLOCKED: localhost not allowed. %s → %s", r.url, r.resolved_ips)
            return

        if r.is_private and r.private_cidr_blocked:
            r.blocked_by_policy = True
            r.policy_block_reason = (
                f'目标地址解析为内网地址 ({r.resolved_ips})，'
                f'但 PERF_BLOCK_PRIVATE_CIDRS=True。'
            )
            r.error_summary = r.policy_block_reason
            logger.warning("Probe BLOCKED: private CIDR not allowed. %s → %s", r.url, r.resolved_ips)
            return

        # ── 白名单 ──────────────────────────────────────────────
        allowed_hosts = _get_conf('PERF_ALLOWED_HOSTS', [])
        if allowed_hosts:
            hostname_lower = r.hostname.lower()
            allowed = any(
                hostname_lower == h.lower() or hostname_lower.endswith('.' + h.lower())
                for h in allowed_hosts
            )
            # 检查 IP 是否在白名单中
            allowed = allowed or any(ip in allowed_hosts for ip in r.resolved_ips)
            if not allowed:
                r.blocked_by_policy = True
                r.policy_block_reason = (
                    f'目标 "{r.hostname}" 不在 PERF_ALLOWED_HOSTS 白名单中'
                )
                r.error_summary = r.policy_block_reason
                logger.warning("Probe BLOCKED: not in allowlist. %s", r.url)
                return

    # ── 5. TCP 连通性 ──────────────────────────────────────────

    def _check_tcp(self) -> None:
        """TCP connect 到目标 IP:port。"""
        r = self._result
        if not r.resolved_ips:
            return

        timeout = r.probe_timeout
        ip = r.resolved_ips[0]

        try:
            start = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((ip, r.port))
            sock.close()
            r.tcp_connect_ok = True
            r.tcp_connect_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.info("Probe TCP: %s:%s → OK (%.1fms)", ip, r.port, r.tcp_connect_ms)

        except socket.timeout:
            r.tcp_connect_error = f'TCP 连接超时 ({timeout}s)'
            r.error_summary = f'{r.hostname}:{r.port} TCP 连接超时'
            logger.warning("Probe TCP timeout: %s:%s", ip, r.port)

        except ConnectionRefusedError:
            r.tcp_connect_error = f'TCP 连接被拒绝: {ip}:{r.port}'
            r.error_summary = f'{r.hostname}:{r.port} 连接被拒绝，服务可能未启动'
            logger.warning("Probe TCP refused: %s:%s", ip, r.port)

        except OSError as exc:
            r.tcp_connect_error = f'TCP 连接失败: {exc}'
            r.error_summary = f'{r.hostname}:{r.port} 连接失败 — {exc}'
            logger.warning("Probe TCP error: %s:%s → %s", ip, r.port, exc)

    # ── 6. HTTP 请求 + TLS ──────────────────────────────────────

    def _check_http(self) -> None:
        """发送 HTTP 请求并检查 TLS。"""
        r = self._result
        timeout = r.probe_timeout

        try:
            start = time.perf_counter()

            # 使用 requests 发送请求
            resp = requests.request(
                method='HEAD' if r.method == 'GET' else r.method,
                url=r.url,
                timeout=timeout,
                allow_redirects=True,
                headers={'User-Agent': 'SyncBoard-PerfProbe/1.0'},
            )

            r.http_ok = True
            r.http_status_code = resp.status_code
            r.http_duration_ms = round((time.perf_counter() - start) * 1000, 1)

            # ── 收集 TLS 信息 ──────────────────────────────────
            if r.scheme == 'https':
                raw = getattr(resp, 'raw', None)
                if raw and hasattr(raw, '_connection'):
                    self._extract_tls_info(resp)

            logger.info(
                "Probe HTTP: %s %s → %s (%.0fms)",
                r.method, r.url, resp.status_code, r.http_duration_ms,
            )

        except requests.exceptions.SSLError as exc:
            r.tls_ok = False
            r.tls_error = str(exc)
            r.http_error = f'TLS/SSL 错误: {exc}'
            r.error_summary = f'{r.url} TLS 证书错误 — {_truncate(str(exc), 200)}'
            logger.warning("Probe TLS error: %s → %s", r.url, exc)

        except requests.exceptions.ConnectionError as exc:
            r.http_error = f'连接失败: {exc}'
            r.error_summary = f'{r.url} 不可达 — {_truncate(str(exc), 200)}'
            logger.warning("Probe connection error: %s → %s", r.url, exc)

        except requests.exceptions.Timeout as exc:
            r.http_error = f'请求超时 ({timeout}s)'
            r.error_summary = f'{r.url} 请求超时 ({timeout}s)'
            logger.warning("Probe HTTP timeout: %s", r.url)

        except Exception as exc:
            r.http_error = str(exc)
            r.error_summary = f'{r.url} 请求异常 — {_truncate(str(exc), 200)}'
            logger.warning("Probe HTTP error: %s → %s", r.url, exc)

    def _extract_tls_info(self, resp) -> None:
        """从响应中提取 TLS 信息。"""
        r = self._result
        try:
            sock = resp.raw._connection.sock
            if hasattr(sock, 'version'):
                r.tls_ok = True
                r.tls_version = str(sock.version())
            if hasattr(sock, 'getpeercert'):
                cert = sock.getpeercert()
                if cert:
                    r.tls_cert_subject = _get_cert_subject(cert)
                    if 'notAfter' in cert:
                        r.tls_cert_expires = cert['notAfter']
        except Exception:
            pass  # TLS 信息提取失败不影响主流程


# ── 工具函数 ──────────────────────────────────────────────────


def _truncate(s: str, max_len: int = 200) -> str:
    """截断字符串。"""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + '...'


def _get_cert_subject(cert: dict) -> str:
    """从 TLS 证书中提取 subject CN。"""
    try:
        for field in cert.get('subject', []):
            for key, value in field:
                if key == 'commonName':
                    return str(value)
    except Exception:
        pass
    return ''


# ── 便捷工厂 ──────────────────────────────────────────────────


def quick_probe(url: str, method: str = 'GET', timeout: float = 5.0) -> ProbeResult:
    """快速执行一次预检（便利函数）。"""
    service = TargetProbeService()
    return service.probe(url, method=method, timeout=timeout)
