"""TargetProbeService 单元测试 — URL 预检、SSRF 策略、安全校验。"""

import pytest
from unittest.mock import patch, MagicMock
from qa_center.execution.probe import (
    TargetProbeService,
    ProbeResult,
)


class TestTargetProbeService:
    """验证 TargetProbeService 的各个检查环节。"""

    # ── Scheme 校验 ──────────────────────────────────────────

    def test_allows_https(self):
        svc = TargetProbeService()
        r = svc.probe('https://example.com/api', timeout=5)
        assert r.scheme == 'https'
        assert r.scheme_allowed is True

    def test_allows_http(self):
        svc = TargetProbeService()
        r = svc.probe('http://example.com/api', timeout=5)
        assert r.scheme == 'http'
        assert r.scheme_allowed is True

    def test_blocks_file_scheme(self):
        svc = TargetProbeService()
        r = svc.probe('file:///etc/passwd', timeout=5)
        assert r.scheme_allowed is False
        assert r.ok is False
        assert r.failure_reason == 'invalid_scheme'

    def test_blocks_ftp_scheme(self):
        svc = TargetProbeService()
        r = svc.probe('ftp://example.com/file', timeout=5)
        assert r.scheme_allowed is False
        assert r.failure_reason == 'invalid_scheme'

    def test_blocks_invalid_url(self):
        svc = TargetProbeService()
        r = svc.probe('not-a-valid-url', timeout=5)
        assert r.ok is False

    # ── DNS 解析 ─────────────────────────────────────────────

    def test_dns_resolves_public_host(self):
        svc = TargetProbeService()
        r = svc.probe('https://example.com/', timeout=10)
        assert r.dns_resolved is True
        assert len(r.resolved_ips) > 0

    def test_dns_fails_nonexistent(self):
        svc = TargetProbeService()
        r = svc.probe('https://this-domain-does-not-exist-12345.com/', timeout=5)
        assert r.dns_resolved is False
        assert r.ok is False

    # ── IP 分类 + 策略 ───────────────────────────────────────

    @patch.object(TargetProbeService, '_check_dns', return_value=True)
    @patch.object(TargetProbeService, '_check_tcp')
    @patch.object(TargetProbeService, '_check_http')
    def test_localhost_blocked_by_default(self, mock_http, mock_tcp, mock_dns):
        """默认 PERF_ALLOW_LOCALHOST=false 时 localhost 应被拦截。"""
        svc = TargetProbeService()
        r = svc._result = ProbeResult(
            url='http://127.0.0.1/api', hostname='127.0.0.1',
        )
        svc._result.resolved_ips = ['127.0.0.1']
        svc._result.localhost_allowed = False  # default
        svc._classify_ips()
        assert r.is_localhost is True
        assert r.blocked_by_policy is True
        assert r.ok is False

    @patch.object(TargetProbeService, '_check_dns', return_value=True)
    @patch.object(TargetProbeService, '_check_tcp')
    @patch.object(TargetProbeService, '_check_http')
    def test_private_cidr_blocked(self, mock_http, mock_tcp, mock_dns):
        svc = TargetProbeService()
        r = svc._result = ProbeResult(
            url='http://192.168.1.1/api', hostname='192.168.1.1',
        )
        svc._result.resolved_ips = ['192.168.1.1']
        svc._result.private_cidr_blocked = True
        svc._classify_ips()
        assert r.is_private is True
        assert r.blocked_by_policy is True

    @patch.object(TargetProbeService, '_check_dns', return_value=True)
    @patch.object(TargetProbeService, '_check_tcp')
    @patch.object(TargetProbeService, '_check_http')
    def test_public_ip_allowed(self, mock_http, mock_tcp, mock_dns):
        svc = TargetProbeService()
        r = svc._result = ProbeResult(
            url='https://93.184.216.34/api', hostname='93.184.216.34',
        )
        svc._result.resolved_ips = ['93.184.216.34']
        svc._result.localhost_allowed = False
        svc._result.private_cidr_blocked = True
        svc._classify_ips()
        assert r.is_localhost is False
        assert r.is_private is False
        assert r.blocked_by_policy is False

    # ── 云 metadata 拦截 ─────────────────────────────────────

    def test_blocks_aws_metadata(self):
        svc = TargetProbeService()
        r = svc.probe('http://169.254.169.254/latest/meta-data/', timeout=5)
        assert r.blocked_by_policy is True or r.ok is False
        if r.blocked_by_policy:
            assert 'metadata' in r.policy_block_reason.lower()

    def test_blocks_gcp_metadata(self):
        svc = TargetProbeService()
        r = svc._result = ProbeResult(
            url='http://metadata.google.internal/', hostname='metadata.google.internal',
        )
        ok = svc._check_policy()
        assert ok is False
        assert svc._result.blocked_by_policy is True

    # ── to_dict 序列化 ───────────────────────────────────────

    def test_to_dict_contains_all_keys(self):
        svc = TargetProbeService()
        r = svc.probe('https://example.com/', timeout=10)
        d = r.to_dict()
        required = ['ok', 'failure_reason', 'scheme', 'hostname', 'dns_resolved',
                     'resolved_ips', 'is_localhost', 'blocked_by_policy',
                     'tcp_connect_ok', 'http_status_code']
        for key in required:
            assert key in d, f'Missing key: {key}'

    # ── ProbeResult 属性 ─────────────────────────────────────

    def test_is_localhost_warning(self):
        r = ProbeResult(is_localhost=True, localhost_allowed=True)
        assert r.is_localhost_warning is True

        r2 = ProbeResult(is_localhost=True, localhost_allowed=False)
        assert r2.is_localhost_warning is False
