import uuid

import pytest
from rest_framework.test import APIRequestFactory

from qa_center.serializers import TestEnvironmentSerializer
from qa_center.views_environment import TestEnvironmentViewSet
from room.models import AuditLog, ProjectMember, ProjectRole


@pytest.fixture
def project_admin_role(db, mock_project):
    role, _ = ProjectRole.objects.get_or_create(
        project=mock_project,
        key="admin",
        defaults={
            "name": "Admin",
            "permissions": ["project:settings"],
            "is_system": True,
        },
    )
    return role


@pytest.fixture
def project_viewer_role(db, mock_project):
    role, _ = ProjectRole.objects.get_or_create(
        project=mock_project,
        key="viewer",
        defaults={
            "name": "Viewer",
            "permissions": [],
            "is_system": True,
        },
    )
    return role


@pytest.fixture
def other_user(db):
    from django.contrib.auth.models import User

    return User.objects.create_user(
        username="other_user",
        password="pass123456",
        email="other@example.com",
    )


@pytest.fixture
def admin_member(db, mock_project, other_user, project_admin_role):
    mock_project.members.add(other_user)
    return ProjectMember.objects.create(
        project=mock_project,
        user=other_user,
        role=project_admin_role,
    )


@pytest.fixture
def viewer_member(db, mock_project, other_user, project_viewer_role):
    mock_project.members.add(other_user)
    return ProjectMember.objects.create(
        project=mock_project,
        user=other_user,
        role=project_viewer_role,
    )


def _serializer_for(instance, user, data):
    request = APIRequestFactory().patch("/api/qa/environments/")
    request.user = user
    return TestEnvironmentSerializer(
        instance=instance,
        data=data,
        partial=True,
        context={"request": request},
    )


@pytest.mark.parametrize(
    "bad_host",
    [
        "https://example.com",
        "example.com/path",
        "example.com?x=1",
        "example.com#fragment",
        "example.com:8443",
        "*.example.com",
    ],
)
def test_allowed_hosts_rejects_scheme_path_wildcard_and_port(
    db,
    mock_environment,
    mock_user,
    bad_host,
):
    serializer = _serializer_for(
        mock_environment,
        mock_user,
        {"allowed_hosts": [bad_host]},
    )

    assert serializer.is_valid() is False
    assert "allowed_hosts" in serializer.errors


@pytest.mark.parametrize(
    "bad_cidr",
    [
        "127.0.0.0/8",
        "169.254.0.0/16",
        "224.0.0.0/4",
        "0.0.0.0/0",
        "::1/128",
        "fe80::/10",
        "169.254.169.254/32",
        "8.8.8.0/24",
    ],
)
def test_allowed_cidrs_rejects_loopback_linklocal_metadata_reserved_ranges(
    db,
    mock_environment,
    mock_user,
    bad_cidr,
):
    serializer = _serializer_for(
        mock_environment,
        mock_user,
        {"allowed_cidrs": [bad_cidr]},
    )

    assert serializer.is_valid() is False
    assert "allowed_cidrs" in serializer.errors


def test_project_member_without_admin_cannot_update_allowlist(
    db,
    mock_environment,
    viewer_member,
):
    factory = APIRequestFactory()
    request = factory.patch(
        f"/api/qa/environments/{mock_environment.id}/",
        {
            "allowed_hosts": ["internal.example.com"],
            "allowed_cidrs": ["10.0.0.0/8"],
        },
        format="json",
    )
    request.user = viewer_member.user
    view = TestEnvironmentViewSet.as_view({"patch": "partial_update"})

    response = view(request, pk=mock_environment.id)

    assert response.status_code == 403


def test_project_owner_can_update_allowlist_and_audit_is_created(
    db,
    mock_environment,
    mock_user,
):
    factory = APIRequestFactory()
    request = factory.patch(
        f"/api/qa/environments/{mock_environment.id}/",
        {
            "allowed_hosts": ["Internal.Example.com"],
            "allowed_cidrs": ["10.0.0.0/8"],
        },
        format="json",
        HTTP_USER_AGENT="pytest-agent",
        REMOTE_ADDR="127.0.0.1",
    )
    request.user = mock_user
    request.META["HTTP_X_REQUEST_ID"] = str(uuid.uuid4())
    view = TestEnvironmentViewSet.as_view({"patch": "partial_update"})

    response = view(request, pk=mock_environment.id)

    assert response.status_code == 200
    mock_environment.refresh_from_db()
    assert mock_environment.allowed_hosts == ["internal.example.com"]
    assert mock_environment.allowed_cidrs == ["10.0.0.0/8"]

    audit = AuditLog.objects.filter(
        action="qa_env_allowlist_updated",
        resource_type="qa_test_environment",
        resource_id=str(mock_environment.id),
    ).latest("created_at")
    assert audit.user_id == mock_user.id
    assert audit.detail["project_id"] == str(mock_environment.project_id)
    assert audit.detail["environment_id"] == mock_environment.id
    assert audit.detail["before"]["allowed_hosts"] == []
    assert audit.detail["after"]["allowed_hosts"] == ["internal.example.com"]
    assert audit.detail["before"]["allowed_cidrs"] == []
    assert audit.detail["after"]["allowed_cidrs"] == ["10.0.0.0/8"]


def test_project_admin_role_can_update_allowlist_and_audit_is_created(
    db,
    mock_environment,
    admin_member,
):
    factory = APIRequestFactory()
    request = factory.patch(
        f"/api/qa/environments/{mock_environment.id}/",
        {
            "allowed_hosts": ["corp.example.com"],
            "allowed_cidrs": ["192.168.0.0/16"],
        },
        format="json",
        HTTP_USER_AGENT="pytest-agent",
    )
    request.user = admin_member.user
    request.META["HTTP_X_REQUEST_ID"] = str(uuid.uuid4())
    view = TestEnvironmentViewSet.as_view({"patch": "partial_update"})

    response = view(request, pk=mock_environment.id)

    assert response.status_code == 200
    audit = AuditLog.objects.filter(
        action="qa_env_allowlist_updated",
        resource_type="qa_test_environment",
        resource_id=str(mock_environment.id),
        user=admin_member.user,
    ).latest("created_at")
    assert audit.detail["after"]["allowed_hosts"] == ["corp.example.com"]
