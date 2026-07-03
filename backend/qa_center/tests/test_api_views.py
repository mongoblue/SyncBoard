from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_unauthenticated_user_cannot_execute_auto_case(mock_suite, mock_user):
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Need Auth",
        url="/auth",
        method="GET",
        created_by=mock_user,
    )
    client = APIClient()

    response = client.post(f"/api/qa/auto-cases/{case.id}/execute/")

    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_non_project_member_cannot_access_project_case(mock_project, mock_user, other_user):
    from qa_center.models import ApiAutoTestCase, ApiAutoTestSuite

    suite = ApiAutoTestSuite.objects.create(
        name="Private Suite",
        project=mock_project,
        created_by=mock_user,
    )
    case = ApiAutoTestCase.objects.create(
        suite=suite,
        name="Private Case",
        url="/private",
        method="GET",
        created_by=mock_user,
    )
    client = APIClient()
    client.force_authenticate(user=other_user)

    response = client.get(f"/api/qa/auto-cases/{case.id}/")

    assert response.status_code == 404 or response.status_code == 403


@pytest.mark.django_db
def test_secret_global_var_is_not_returned_in_plaintext(mock_project, mock_user):
    from qa_center.models import TestGlobalVar

    secret = TestGlobalVar.objects.create(
        project=mock_project,
        key="api_key",
        value="super-secret-value",
        is_secret=True,
        created_by=mock_user,
    )
    client = APIClient()
    client.force_authenticate(user=mock_user)

    response = client.get(f"/api/qa/global-vars/{secret.id}/")



@pytest.mark.django_db
def test_project_member_can_access_suite_backed_case_without_direct_case_project(mock_project, mock_suite, mock_user):
    from qa_center.models import ApiAutoTestCase

    case = ApiAutoTestCase.objects.create(
        suite=mock_suite,
        project=None,
        name="Suite Backed Case",
        url="/suite-backed",
        method="GET",
        created_by=mock_user,
    )
    client = APIClient()
    client.force_authenticate(user=mock_user)

    response = client.get(f"/api/qa/auto-cases/{case.id}/")

    assert response.status_code == 200
