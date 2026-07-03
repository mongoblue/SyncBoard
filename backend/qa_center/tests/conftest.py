import pytest
from django.contrib.auth.models import User
from room.models import Project
from qa_center.models import (
    ApiAutoTestSuite,
    ApiAutoTestCase,
    CiCdConfig,
    TestEnvironment,
    TestGlobalVar,
)


@pytest.fixture
def mock_user(db):
    return User.objects.create_user(
        username="qa_tester",
        password="testpass123",
        email="qa@test.com",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="qa_other_user",
        password="testpass123",
        email="other@test.com",
    )


@pytest.fixture
def mock_project(db, mock_user):
    project = Project.objects.create(
        name="Test Project",
        owner=mock_user,
    )
    project.members.add(mock_user)
    return project


@pytest.fixture
def mock_environment(db, mock_project, mock_user):
    return TestEnvironment.objects.create(
        name="Test Env",
        project=mock_project,
        base_url="https://httpbin.org",
        variables={"api_key": "test-key-123", "version": "v1"},
        allowed_hosts=[],
        allowed_cidrs=[],
        created_by=mock_user,
    )


@pytest.fixture
def mock_suite(db, mock_project, mock_user):
    return ApiAutoTestSuite.objects.create(
        name="Test Suite",
        project=mock_project,
        created_by=mock_user,
    )


@pytest.fixture
def mock_global_var(db, mock_project, mock_user):
    return TestGlobalVar.objects.create(
        project=mock_project,
        key="global_token",
        value="global-token-value",
        created_by=mock_user,
    )


@pytest.fixture
def mock_case(db, mock_suite, mock_user):
    return ApiAutoTestCase.objects.create(
        suite=mock_suite,
        name="Test Case",
        url="/get",
        method="GET",
        headers={"Authorization": "Bearer {{global_token}}"},
        created_by=mock_user,
    )


@pytest.fixture
def cicd_config(db, mock_project, mock_user):
    return CiCdConfig.objects.create(
        name="CI Config",
        ci_type="gitlab",
        branch="main",
        project=mock_project,
        created_by=mock_user,
        is_active=True,
        ci_url="https://ci.example.test",
        ci_project="group/project",
        ci_token="token-123456",
    )
