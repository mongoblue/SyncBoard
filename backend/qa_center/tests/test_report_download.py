"""测试报告导出（download_report）测试。"""
import json

import pytest
from django.utils import timezone

from qa_center.models import TestResult


@pytest.mark.django_db
def test_download_report_returns_html_attachment(mock_project, mock_user):
    tr = TestResult.objects.create(
        test_type='api',
        name='Report Case',
        project=mock_project,
        status='passed',
        executed_by=mock_user,
        started_at=timezone.now(),
        completed_at=timezone.now(),
        duration_ms=1200,
        test_log=json.dumps({
            'summary': {'total': 2, 'passed': 1, 'failed': 1, 'pass_rate': 50},
            'results': [
                {'case_id': 1, 'case_name': 'ok-case', 'type': 'api',
                 'passed': True, 'status_code': 200, 'response_time_ms': 12},
                {'case_id': 2, 'case_name': 'bad-case', 'type': 'api',
                 'passed': False, 'status_code': 500,
                 'error_message': '<script>alert(1)</script> 服务异常'},
            ],
        }, ensure_ascii=False),
    )

    client = __import__('rest_framework.test', fromlist=['APIClient']).APIClient()
    client.force_authenticate(user=mock_user)
    resp = client.get(f'/api/qa/test-results/{tr.id}/download_report/')

    assert resp.status_code == 200
    assert resp['Content-Type'].startswith('text/html')
    assert 'attachment; filename=' in resp['Content-Disposition']
    body = resp.content.decode('utf-8')

    # 概要卡片
    assert 'Report Case' in body
    assert '通过率' in body
    assert '50%' in body
    # 用例明细
    assert 'ok-case' in body
    assert 'bad-case' in body
    # XSS 转义：错误信息里的脚本标签不应原样出现
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;' in body


@pytest.mark.django_db
def test_download_report_without_log_still_renders(mock_project, mock_user):
    tr = TestResult.objects.create(
        test_type='ui',
        name='Empty Log Report',
        project=mock_project,
        status='running',
        executed_by=mock_user,
        started_at=timezone.now(),
        test_log=None,
    )

    client = __import__('rest_framework.test', fromlist=['APIClient']).APIClient()
    client.force_authenticate(user=mock_user)
    resp = client.get(f'/api/qa/test-results/{tr.id}/download_report/')

    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    assert 'Empty Log Report' in body
    assert '无用例明细' in body
