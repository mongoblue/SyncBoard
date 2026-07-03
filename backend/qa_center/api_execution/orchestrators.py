from __future__ import annotations

from django.utils import timezone

from qa_center import template_engine as te
from qa_center.metrics import generate_trace_id

from .adapters import ApiAutoTestCaseAdapter
from .contracts import ApiExecutionContext
from .mappers import ApiAutoTestCaseResultMapper, ApiAutoTestResultAggregator
from .runner import UnifiedApiRunner
from .runtime_guard import RuntimeGuard
from .transport import MockTransport, RequestsTransport, SSRFProtectedRequestsTransport
from qa_center.result_sink import mirror_to_test_result, sync_unified_run_from_auto_result


class ApiAutoSingleCaseOrchestrator:
    def __init__(self, *, case, user, test_result, source="single", skip_sync=False):
        self.case = case
        self.user = user
        self.test_result = test_result
        self.source = source
        self.skip_sync = skip_sync
        self.guard = RuntimeGuard()
        self.adapter = ApiAutoTestCaseAdapter()
        self.mapper = ApiAutoTestCaseResultMapper()

    def execute(self):
        definition = self.adapter.adapt(self.case)
        project = self.case.project or (self.case.suite.project if self.case.suite_id else None)
        if project is None:
            raise ValueError("用例未关联项目（既无 project 也无 suite）")
        env = self.case.environment or _resolve_environment(project)
        _, global_vars = _resolve_environment_and_globals(project)
        transport, runtime_mode = _build_transport(self.guard)
        context = _build_execution_context(
            project=project,
            environment=env,
            global_vars=global_vars,
            chain_vars={},
            trace_id=generate_trace_id(),
            runtime_mode=runtime_mode,
            source="api_auto_case_execute",
            guard=self.guard,
        )

        runner = UnifiedApiRunner(transport=transport)
        execution_result = runner.run(definition, context)
        case_result = self.mapper.create_case_result(
            case=self.case,
            test_result=self.test_result,
            execution_result=execution_result,
        )
        self.test_result = self.mapper.finalize_test_result(
            test_result=self.test_result,
            case_result=case_result,
            execution_result=execution_result,
        )
        self.test_result.completed_at = timezone.now()
        self.test_result.save()
        if not self.skip_sync:
            sync_unified_run_from_auto_result(
                auto_result=self.test_result,
                case_result=case_result,
                source=self.source,
            )
            mirror_to_test_result(auto_result=self.test_result, source=self.source)
        return {
            "test_result": self.test_result,
            "case_result": case_result,
            "runtime_mode": runtime_mode,
        }


def create_api_auto_single_case_orchestrator(*, case, user, test_result, source="single", skip_sync=False):
    return ApiAutoSingleCaseOrchestrator(case=case, user=user, test_result=test_result, source=source, skip_sync=skip_sync)


class ApiAutoSuiteOrchestrator:
    def __init__(self, *, suite, user):
        self.suite = suite
        self.user = user
        self.guard = RuntimeGuard()
        self.adapter = ApiAutoTestCaseAdapter()
        self.mapper = ApiAutoTestCaseResultMapper()
        self.aggregator = ApiAutoTestResultAggregator()

    def execute(self):
        active_cases = (
            self.suite.test_cases
            .filter(is_active=True)
            .prefetch_related("assertions", "extractors")
            .order_by("sort_order", "created_at")
        )
        test_result = self.suite.test_results.model.objects.create(
            suite=self.suite,
            name=f"{self.suite.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
            status="running",
            total_cases=active_cases.count(),
            passed_cases=0,
            failed_cases=0,
            error_cases=0,
            duration_ms=0,
            executed_by=self.user,
            started_at=timezone.now(),
        )

        env, global_vars = _resolve_environment_and_globals(self.suite.project)
        transport, runtime_mode = _build_transport(self.guard)
        runner = UnifiedApiRunner(transport=transport)
        chain_vars = {}

        for case in active_cases:
            definition = self.adapter.adapt(case)
            context = _build_execution_context(
                project=self.suite.project,
                environment=env,
                global_vars=global_vars,
                chain_vars=dict(chain_vars),
                trace_id=generate_trace_id(),
                runtime_mode=runtime_mode,
                source="api_auto_suite_execute",
                guard=self.guard,
            )
            execution_result = runner.run(definition, context)
            case_result = self.mapper.create_case_result(
                case=case,
                test_result=test_result,
                execution_result=execution_result,
            )
            test_result = self.aggregator.update_counts(
                test_result=test_result,
                execution_result=execution_result,
                case_result=case_result,
            )
            if execution_result.status == "passed" and execution_result.runtime_outputs.eligible_for_chain:
                chain_vars.update(execution_result.runtime_outputs.extracted_variables)

        test_result.completed_at = timezone.now()
        test_result.save()
        sync_unified_run_from_auto_result(auto_result=test_result, source="single")
        mirror_to_test_result(auto_result=test_result, source="single")
        return {
            "test_result": test_result,
            "runtime_mode": runtime_mode,
        }


def create_api_auto_suite_orchestrator(*, suite, user):
    return ApiAutoSuiteOrchestrator(suite=suite, user=user)


def _resolve_environment_and_globals(project):
    env = _resolve_environment(project)
    globals_ = te.load_project_globals(project)
    global_vars = {item.key: item.value for item in globals_}
    return env, global_vars


def _resolve_environment(project):
    return te.resolve_project_environment(project)


def _build_execution_context(
    *,
    project,
    environment,
    global_vars,
    chain_vars,
    trace_id,
    runtime_mode,
    source,
    guard,
):
    return ApiExecutionContext(
        trace_id=trace_id,
        project_id=str(project.id),
        environment_id=str(environment.id) if environment else "",
        system_vars={
            "base_url": getattr(environment, "base_url", "") or "",
            "project_id": str(project.id),
            "environment_id": str(environment.id) if environment else "",
        },
        global_vars=global_vars,
        environment_vars=getattr(environment, "variables", {}) or {},
        run_overrides={},
        chain_vars=chain_vars,
        locked_variables={"base_url", "project_id", "environment_id"},
        secret_names={
            *(name.lower() for name, value in global_vars.items() if value),
            "authorization",
            "token",
            "password",
            "secret",
            "api_key",
            "cookie",
            "set-cookie",
        },
        secret_values={value for value in global_vars.values() if isinstance(value, str)},
        policies={
            "allowed_hosts": getattr(environment, "allowed_hosts", []) or [],
            "allowed_cidrs": getattr(environment, "allowed_cidrs", []) or [],
            "app_env": guard.get_app_env(),
        },
        runtime_mode=runtime_mode,
        metadata={"source": source},
    )


def _build_transport(guard):
    transport_name = guard.choose_default_transport()
    if transport_name == "mock_transport":
        return MockTransport(), guard.build_runtime_mode(is_mock=True)
    if transport_name == "ssrf_protected_requests_transport":
        return SSRFProtectedRequestsTransport(), guard.build_runtime_mode(is_mock=False)
    return RequestsTransport(), guard.build_runtime_mode(is_mock=False)
