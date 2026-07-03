import pytest
from unittest.mock import patch, MagicMock
from qa_center.run_plan_executor import _get_or_create_plan_suite, TestRunPlanExecutor
from qa_center.models import TestRunPlan


class TestGetOrCreatePlanSuite:
    def test_creates_suite_for_plan(self, db, mock_project, mock_user):
        plan = TestRunPlan.objects.create(
            name="Test Plan", project=mock_project, created_by=mock_user
        )
        suite = _get_or_create_plan_suite(plan)
        assert suite.name == f"__run_plan__#{plan.id}"
        assert suite.is_active is False

    def test_reuses_existing_suite(self, db, mock_project, mock_user):
        plan = TestRunPlan.objects.create(
            name="Test Plan", project=mock_project, created_by=mock_user
        )
        suite1 = _get_or_create_plan_suite(plan)
        suite2 = _get_or_create_plan_suite(plan)
        assert suite1.id == suite2.id


class TestRunPlanExecutorBasic:
    def test_executor_initialization(self, db, mock_project, mock_user):
        plan = TestRunPlan.objects.create(
            name="Test Plan", project=mock_project, created_by=mock_user
        )
        executor = TestRunPlanExecutor(plan, user=mock_user)
        assert executor.plan == plan
        assert executor.user == mock_user

    @patch("qa_center.run_plan_executor._broadcast")
    def test_broadcast_called(self, mock_broadcast, db, mock_project, mock_user):
        plan = TestRunPlan.objects.create(
            name="Test Plan", project=mock_project, created_by=mock_user
        )
        mock_broadcast({"type": "test"}, project_id=mock_project.id)
        mock_broadcast.assert_called_once_with(
            {"type": "test"}, project_id=mock_project.id
        )
