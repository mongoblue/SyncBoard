"""UI test views: sync/async dual-track + env vars."""

import base64
import logging
import os
import threading
import uuid
from datetime import datetime

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from room.project_access import ensure_project_id_access, project_access_q

from .models import TestResult, TestScreenshot, UiTestCase
from .serializers import UiTestCaseListSerializer, UiTestCaseSerializer
from .ui_execution import (
    UiConcurrencyLimitError,
    prepare_and_execute_ui_case,
    prepare_ui_case_payload,
)
from .workers import runner_supervisor
from .workers.runner_supervisor import execute_ui_case

logger = logging.getLogger('qa_center.runner')



def _playwright_temp_root():
    return os.path.realpath(os.path.join(settings.BASE_DIR, '.playwright-temp'))


def _path_is_under(path, root):
    try:
        abs_path = os.path.realpath(path)
        abs_root = os.path.realpath(root)
        return os.path.commonpath([abs_path, abs_root]) == abs_root
    except ValueError:
        return False


def _ensure_test_result_access(user, test_result, message='无权访问该测试结果'):
    if test_result.project_id:
        ensure_project_id_access(user, test_result.project_id)
        return
    if test_result.executed_by_id != user.id:
        raise PermissionDenied(message)


def _ensure_test_result_screenshot_access(user, test_result):
    _ensure_test_result_access(user, test_result, '无权访问该截图')


def _get_latest_ui_result_for_task(task_id):
    return (
        TestResult.objects.select_related('project', 'executed_by')
        .filter(task_id=task_id)
        .order_by('-started_at', '-created_at')
        .first()
    )


def _get_authorized_ui_result_for_task(user, task_id):
    test_result = _get_latest_ui_result_for_task(task_id)
    if test_result is None:
        raise Http404()
    _ensure_test_result_access(user, test_result)
    return test_result


def _open_png_response(path):
    return FileResponse(open(path, 'rb'), content_type='image/png')


def _parse_environment_id(data):
    raw = None
    if data is not None:
        raw = data.get('environment_id', data.get('environment'))
    if raw in (None, '', 'null'):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _events_to_payload(events, result, *, task_id='', include_base64=True):
    logs = []
    step_screenshots = []
    error_msg = None
    error_code = None
    resolved_task_id = task_id or result.get('task_id') or ''

    for ev in events:
        t = ev.get('type')
        if not resolved_task_id and ev.get('task_id'):
            resolved_task_id = ev.get('task_id')
        if t == 'step_log':
            logs.append(ev.get('message', ''))
        elif t == 'step_screenshot' and ev.get('path'):
            item = {
                'step': ev.get('index', 0) + 1,
                'index': ev.get('index', 0),
                'path': ev.get('path'),
            }
            if resolved_task_id:
                item['url'] = f"/api/qa/ui-run/{resolved_task_id}/screenshot/{ev.get('index', 0)}/"
            if include_base64:
                try:
                    with open(ev['path'], 'rb') as f:
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                    item['screenshot'] = f'data:image/png;base64,{b64}'
                except Exception as exc:
                    logger.warning('读取截图失败: %s (%s)', ev.get('path'), exc)
            step_screenshots.append(item)
        elif t == 'error':
            error_msg = ev.get('message', '')
            error_code = ev.get('code')
        elif t == 'step_done' and not ev.get('success'):
            error_msg = error_msg or ev.get('message', '')
            error_code = error_code or ev.get('code')

    return {
        'success': result.get('success', False),
        'logs': logs,
        'step_screenshots': step_screenshots,
        'error': error_msg,
        'error_code': error_code,
        'summary': result.get('summary', {}),
        'task_id': resolved_task_id,
        'aborted': bool(result.get('aborted')),
    }


def _persist_ui_test_result(
    *,
    name,
    project,
    ui_test_case,
    user,
    result,
    events,
    task_id='',
    env_meta=None,
    original_steps=None,
    status_override=None,
    existing=None,
):
    error_msg = ''
    error_code = None
    error_tb = ''
    worker_pid = None
    task_id = task_id or ''
    temp_dir_path = ''
    started_at = None

    for ev in events:
        t = ev.get('type')
        if t == 'error':
            error_msg = error_msg or ev.get('message', '')
            error_code = error_code or ev.get('code')
            error_tb = error_tb or ev.get('traceback', '')
        elif t == 'step_done' and not ev.get('success'):
            error_msg = error_msg or ev.get('message', '')
            error_code = error_code or ev.get('code')
            error_tb = error_tb or ev.get('traceback', '')
        elif t == 'supervisor_meta':
            if not task_id:
                task_id = ev.get('task_id', '') or task_id
            if ev.get('worker_pid') is not None:
                worker_pid = ev.get('worker_pid')
        elif t == 'started':
            temp_dir_path = ev.get('temp_dir', '') or temp_dir_path
            started_at = started_at or timezone.now()

    aborted = bool(result.get('aborted')) or (error_code == 'ABORTED')
    if status_override:
        status_value = status_override
    elif aborted:
        status_value = 'error'
    else:
        status_value = 'passed' if result.get('success') else 'failed'

    env_meta = env_meta or {}
    test_params = {
        'environment_id': env_meta.get('environment_id'),
        'environment_name': env_meta.get('environment_name') or '',
        'base_url': env_meta.get('base_url') or '',
        'unresolved_variables': env_meta.get('unresolved_variables') or [],
        'variables_preview': env_meta.get('variables_preview') or {},
        'original_url': env_meta.get('original_url') or '',
        'task_id': task_id,
    }

    completed_at = timezone.now()
    if started_at is None:
        started_at = completed_at
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    fields = dict(
        test_type='ui',
        name=name,
        project=project,
        ui_test_case=ui_test_case,
        executed_by=user,
        status=status_value,
        lifecycle_state='stopped' if aborted else ('passed' if status_value == 'passed' else 'failed'),
        lifecycle_reason='user_aborted' if aborted else '',
        test_steps=original_steps if original_steps is not None else (getattr(ui_test_case, 'steps', None) or []),
        actual_result='测试完成' if result.get('success') else (error_msg or '失败'),
        error_message=error_msg,
        task_id=task_id,
        error_code=error_code or ('ABORTED' if aborted else ''),
        error_traceback=error_tb,
        worker_pid=worker_pid,
        temp_dir_path=temp_dir_path or '',
        aborted=aborted,
        test_log='\n'.join(ev.get('message', '') for ev in events if ev.get('type') == 'step_log'),
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        test_environment=env_meta.get('environment_name') or '',
        test_params=test_params,
        source='single',
    )

    try:
        if existing is not None:
            for k, v in fields.items():
                setattr(existing, k, v)
            existing.save()
            test_result = existing
        else:
            test_result = TestResult.objects.create(**fields)
    except Exception:
        logger.exception('保存 TestResult 失败')
        return None

    if existing is not None:
        try:
            test_result.screenshots.all().delete()
        except Exception:
            logger.exception('清理旧截图失败')

    for ev in events:
        if ev.get('type') == 'step_screenshot' and ev.get('path'):
            try:
                with open(ev['path'], 'rb') as f:
                    image_data = f.read()
                idx = ev.get('index', 0)
                fname = f"ui_test_step{idx}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"
                rel_dir = os.path.join('test_screenshots', datetime.now().strftime('%Y/%m/%d'))
                full_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
                os.makedirs(full_dir, exist_ok=True)
                with open(os.path.join(full_dir, fname), 'wb') as f:
                    f.write(image_data)
                TestScreenshot.objects.create(
                    test_result=test_result,
                    name=f'步骤 {idx + 1} 截图',
                    image=os.path.join(rel_dir, fname),
                    step_index=idx,
                )
            except Exception:
                logger.exception('保存截图失败')

    debug = os.environ.get('UI_TEST_DEBUG', '').lower() in ('1', 'true', 'yes')
    if temp_dir_path and os.path.isdir(temp_dir_path) and not debug:
        try:
            import shutil
            if _path_is_under(temp_dir_path, _playwright_temp_root()):
                shutil.rmtree(temp_dir_path, ignore_errors=True)
        except Exception:
            logger.exception('清理 worker temp_dir 失败: %s', temp_dir_path)

    try:
        from .result_sink import sync_ui_run_from_test_result
        sync_ui_run_from_test_result(test_result=test_result)
    except Exception:
        logger.exception('sync_ui_run_from_test_result 失败')

    return test_result


class UiTestCaseViewSet(viewsets.ModelViewSet):
    """UI 测试用例 ViewSet"""

    permission_classes = [IsAuthenticated]
    serializer_class = UiTestCaseSerializer

    def get_queryset(self):
        queryset = UiTestCase.objects.filter(
            project_access_q('project', self.request.user)
        ).distinct()
        project_id = self.request.query_params.get('project')
        if project_id:
            ensure_project_id_access(self.request.user, project_id)
            queryset = queryset.filter(project_id=project_id)
        return queryset.select_related('project', 'created_by', 'environment')

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        obj = get_object_or_404(
            UiTestCase.objects.select_related('project', 'created_by', 'environment'),
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]},
        )
        ensure_project_id_access(self.request.user, obj.project_id)
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return UiTestCaseListSerializer
        return UiTestCaseSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            ensure_project_id_access(self.request.user, project.id)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        project = serializer.validated_data.get('project')
        if project:
            ensure_project_id_access(self.request.user, project.id)
        serializer.save()

    def _run_case_sync(self, test_case, request, *, environment_id=None):
        events = []
        try:
            result, env_meta, _case_data = prepare_and_execute_ui_case(
                test_case.project,
                url=test_case.url,
                steps=test_case.steps or [],
                case=test_case,
                case_id=test_case.id,
                environment_id=environment_id,
                on_event=events.append,
            )
        except UiConcurrencyLimitError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                    'error_code': 'CONCURRENCY_LIMIT',
                    'max_concurrent': exc.max_concurrent,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        task_id = result.get('task_id') or ''
        payload = _events_to_payload(events, result, task_id=task_id)
        try:
            tr = _persist_ui_test_result(
                name=test_case.name,
                project=test_case.project,
                ui_test_case=test_case,
                user=request.user,
                result=result,
                events=events,
                task_id=task_id,
                env_meta=env_meta,
                original_steps=test_case.steps or [],
            )
            if tr is not None:
                payload['result_id'] = tr.id
        except Exception:
            logger.exception('_persist_ui_test_result 失败')
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        test_case = self.get_object()
        environment_id = _parse_environment_id(request.data)
        return self._run_case_sync(test_case, request, environment_id=environment_id)

    @action(detail=True, methods=['post'], url_path='run_async')
    def run_async(self, request, pk=None):
        test_case = self.get_object()
        environment_id = _parse_environment_id(request.data)
        task_id = uuid.uuid4().hex

        case_data, env_meta = prepare_ui_case_payload(
            test_case.project,
            url=test_case.url,
            steps=test_case.steps or [],
            case=test_case,
            case_id=test_case.id,
            environment_id=environment_id,
        )
        tr = TestResult.objects.create(
            test_type='ui',
            name=test_case.name,
            project=test_case.project,
            ui_test_case=test_case,
            executed_by=request.user,
            status='running',
            lifecycle_state='running',
            test_steps=test_case.steps or [],
            task_id=task_id,
            test_environment=env_meta.get('environment_name') or '',
            test_params={
                **{k: env_meta.get(k) for k in (
                    'environment_id', 'environment_name', 'base_url',
                    'unresolved_variables', 'variables_preview', 'original_url',
                )},
                'task_id': task_id,
                'mode': 'async',
            },
            started_at=timezone.now(),
            source='single',
        )

        def _worker():
            events = []
            try:
                result = runner_supervisor.execute_ui_case(
                    case_data,
                    on_event=events.append,
                    task_id=task_id,
                )
            except UiConcurrencyLimitError as exc:
                tr.status = 'error'
                tr.lifecycle_state = 'error'
                tr.error_code = 'CONCURRENCY_LIMIT'
                tr.error_message = str(exc)
                tr.completed_at = timezone.now()
                tr.save(update_fields=[
                    'status', 'lifecycle_state', 'error_code', 'error_message', 'completed_at',
                ])
                return
            except Exception as exc:
                logger.exception('async UI run 失败: %s', task_id)
                tr.status = 'error'
                tr.lifecycle_state = 'error'
                tr.error_code = 'INTERNAL'
                tr.error_message = str(exc)
                tr.completed_at = timezone.now()
                tr.save(update_fields=[
                    'status', 'lifecycle_state', 'error_code', 'error_message', 'completed_at',
                ])
                return

            try:
                _persist_ui_test_result(
                    name=test_case.name,
                    project=test_case.project,
                    ui_test_case=test_case,
                    user=request.user,
                    result=result,
                    events=events,
                    task_id=task_id,
                    env_meta=env_meta,
                    original_steps=test_case.steps or [],
                    existing=tr,
                )
            except Exception:
                logger.exception('async persist 失败: %s', task_id)

        threading.Thread(target=_worker, name=f'ui-run-{task_id}', daemon=True).start()
        return Response(
            {
                'success': True,
                'task_id': task_id,
                'result_id': tr.id,
                'mode': 'async',
                'message': '已开始后台执行',
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def _save_test_result(self, test_case, result, events, request, task_id=None, env_meta=None):
        return _persist_ui_test_result(
            name=test_case.name,
            project=test_case.project,
            ui_test_case=test_case,
            user=request.user,
            result=result,
            events=events,
            task_id=task_id or '',
            env_meta=env_meta,
            original_steps=test_case.steps or [],
        )

    def _events_to_payload(self, events, result):
        return _events_to_payload(events, result)

    @action(detail=True, methods=['get'], url_path='linked-tasks')
    def linked_tasks(self, request, pk=None):
        test_case = self.get_object()
        tasks = test_case.related_tasks.select_related('column', 'assignee').prefetch_related('tags')
        from room.serializers import TaskSerializer
        return Response(TaskSerializer(tasks, many=True).data)

    @action(detail=False, methods=['post'], url_path=r'runs/(?P<task_id>[^/]+)/abort')
    def abort_run(self, request, task_id=None):
        if not task_id:
            return Response({'error': 'task_id 必填'}, status=status.HTTP_400_BAD_REQUEST)

        tr = _get_authorized_ui_result_for_task(request.user, task_id)
        alive = runner_supervisor.is_runner_alive(task_id)
        if not alive:
            return Response(
                {'task_id': task_id, 'aborted': False, 'message': '运行已结束或不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        ok = runner_supervisor.abort_runner(task_id)
        if not ok:
            return Response(
                {'task_id': task_id, 'aborted': False, 'message': '终止失败，查看服务端日志'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            tr.aborted = True
            tr.status = 'error'
            tr.lifecycle_state = 'stopped'
            tr.lifecycle_reason = 'user_aborted'
            tr.error_code = tr.error_code or 'ABORTED'
            tr.error_message = tr.error_message or '用户中止执行'
            tr.save(update_fields=[
                'aborted', 'status', 'lifecycle_state', 'lifecycle_reason',
                'error_code', 'error_message',
            ])
        except Exception:
            logger.exception('标记 TestResult.aborted 失败: %s', task_id)

        return Response({'task_id': task_id, 'aborted': True}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path=r'runs/(?P<task_id>[^/]+)/events')
    def run_events(self, request, task_id=None):
        if not task_id:
            return Response({'error': 'task_id 必填'}, status=status.HTTP_400_BAD_REQUEST)
        _get_authorized_ui_result_for_task(request.user, task_id)
        evs = runner_supervisor.peek_events(task_id)
        return Response(
            {
                'task_id': task_id,
                'events': evs,
                'finished': any(e.get('type') in ('finished', 'run_finished_persisted') for e in evs),
                'alive': runner_supervisor.is_runner_alive(task_id),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'])
    def run_temp(self, request):
        url = request.data.get('url', '')
        steps = request.data.get('steps', [])
        project_id = request.data.get('project') or request.data.get('project_id')
        environment_id = _parse_environment_id(request.data)
        if not url:
            return Response({'error': '请提供起始 URL'}, status=status.HTTP_400_BAD_REQUEST)
        if not project_id:
            return Response({'error': '请选择项目'}, status=status.HTTP_400_BAD_REQUEST)
        ensure_project_id_access(request.user, project_id)

        from room.models import Project
        project = get_object_or_404(Project, pk=project_id)
        events = []
        try:
            result, env_meta, _case_data = prepare_and_execute_ui_case(
                project,
                url=url,
                steps=steps,
                environment_id=environment_id,
                on_event=events.append,
            )
        except UiConcurrencyLimitError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                    'error_code': 'CONCURRENCY_LIMIT',
                    'max_concurrent': exc.max_concurrent,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        task_id = result.get('task_id') or ''
        payload = _events_to_payload(events, result, task_id=task_id)
        payload['environment'] = {
            'id': env_meta.get('environment_id'),
            'name': env_meta.get('environment_name'),
            'unresolved_variables': env_meta.get('unresolved_variables') or [],
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='run_temp_async')
    def run_temp_async(self, request):
        url = request.data.get('url', '')
        steps = request.data.get('steps', [])
        project_id = request.data.get('project') or request.data.get('project_id')
        environment_id = _parse_environment_id(request.data)
        if not url:
            return Response({'error': '请提供起始 URL'}, status=status.HTTP_400_BAD_REQUEST)
        if not project_id:
            return Response({'error': '请选择项目'}, status=status.HTTP_400_BAD_REQUEST)
        ensure_project_id_access(request.user, project_id)

        from room.models import Project
        project = get_object_or_404(Project, pk=project_id)
        task_id = uuid.uuid4().hex
        case_data, env_meta = prepare_ui_case_payload(
            project,
            url=url,
            steps=steps,
            environment_id=environment_id,
        )
        tr = TestResult.objects.create(
            test_type='ui',
            name=f'临时运行 {url[:80]}',
            project=project,
            ui_test_case=None,
            executed_by=request.user,
            status='running',
            lifecycle_state='running',
            test_steps=steps or [],
            task_id=task_id,
            test_environment=env_meta.get('environment_name') or '',
            test_params={
                **{k: env_meta.get(k) for k in (
                    'environment_id', 'environment_name', 'base_url',
                    'unresolved_variables', 'variables_preview', 'original_url',
                )},
                'task_id': task_id,
                'mode': 'async_temp',
            },
            started_at=timezone.now(),
            source='single',
        )

        def _worker():
            events = []
            try:
                result = runner_supervisor.execute_ui_case(case_data, on_event=events.append, task_id=task_id)
                _persist_ui_test_result(
                    name=tr.name,
                    project=project,
                    ui_test_case=None,
                    user=request.user,
                    result=result,
                    events=events,
                    task_id=task_id,
                    env_meta=env_meta,
                    original_steps=steps or [],
                    existing=tr,
                )
            except Exception as exc:
                logger.exception('run_temp_async 失败: %s', task_id)
                tr.status = 'error'
                tr.error_message = str(exc)
                tr.completed_at = timezone.now()
                tr.save(update_fields=['status', 'error_message', 'completed_at'])

        threading.Thread(target=_worker, name=f'ui-run-temp-{task_id}', daemon=True).start()
        return Response(
            {
                'success': True,
                'task_id': task_id,
                'result_id': tr.id,
                'mode': 'async',
            },
            status=status.HTTP_202_ACCEPTED,
        )



def execute_ui_test_cases(case_ids, *, environment_id=None):
    """批量执行入口（DevOps / RunPlan）。保留返回结构，内部走统一内核。"""
    results = []
    for case_id in case_ids:
        try:
            tc = UiTestCase.objects.select_related('project', 'environment').get(id=case_id)
        except UiTestCase.DoesNotExist:
            results.append({
                'case_id': case_id,
                'case_name': '未知用例',
                'passed': False,
                'message': '测试用例不存在',
            })
            continue

        events = []
        try:
            result, env_meta, case_data = prepare_and_execute_ui_case(
                tc.project,
                url=tc.url,
                steps=tc.steps or [],
                case=tc,
                case_id=tc.id,
                environment_id=environment_id,
                on_event=events.append,
            )
        except UiConcurrencyLimitError as exc:
            results.append({
                'case_id': case_id,
                'case_name': tc.name,
                'passed': False,
                'type': 'ui',
                'message': str(exc),
                'error_code': 'CONCURRENCY_LIMIT',
            })
            continue
        except Exception as exc:
            logger.exception('execute_ui_test_cases 失败: %s', case_id)
            results.append({
                'case_id': case_id,
                'case_name': tc.name,
                'passed': False,
                'type': 'ui',
                'message': str(exc),
            })
            continue

        task_id = result.get('task_id') or ''
        try:
            _persist_ui_test_result(
                name=tc.name,
                project=tc.project,
                ui_test_case=tc,
                user=None,
                result=result,
                events=events,
                task_id=task_id,
                env_meta=env_meta,
                original_steps=tc.steps or [],
            )
        except Exception:
            logger.exception('批量 UI 结果持久化失败: %s', case_id)

        steps_result = []
        for i, step in enumerate(tc.steps or []):
            steps_result.append({
                'step_number': i + 1,
                'action': step.get('action', ''),
                'selector': step.get('selector', ''),
                'value': step.get('value', ''),
                'status': 'passed' if result.get('success') else 'failed',
                'logs': [],
            })
        results.append({
            'case_id': case_id,
            'case_name': tc.name,
            'passed': result.get('success', False),
            'type': 'ui',
            'message': '测试完成' if result.get('success') else '失败',
            'request': {
                'method': 'UI',
                'url': case_data.get('url') or tc.url,
                'headers': {},
                'body': {'steps': case_data.get('steps') or tc.steps or []},
            },
            'response': {
                'status_code': 200 if result.get('success') else 500,
                'body': '',
                'headers': {},
            },
            'steps': steps_result,
            'screenshot_url': None,
            'assertions': [],
            'task_id': task_id,
            'environment_id': env_meta.get('environment_id'),
        })
    return results


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ui_run_screenshot(request):
    path = request.query_params.get('path', '')
    task_id = request.query_params.get('task_id', '')
    if not path:
        return HttpResponseBadRequest('path required')
    if not task_id:
        return HttpResponseBadRequest('task_id required')

    tr = _get_latest_ui_result_for_task(task_id)
    if tr is None:
        raise Http404()
    _ensure_test_result_screenshot_access(request.user, tr)

    safe_root = _playwright_temp_root()
    abs_path = os.path.realpath(path)
    temp_dir = os.path.realpath(tr.temp_dir_path) if tr.temp_dir_path else ''
    if not _path_is_under(abs_path, safe_root):
        return HttpResponseBadRequest('invalid path')
    if not temp_dir or not _path_is_under(temp_dir, safe_root) or not _path_is_under(abs_path, temp_dir):
        return HttpResponseBadRequest('invalid path')
    if not os.path.exists(abs_path):
        raise Http404()
    return _open_png_response(abs_path)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ui_run_screenshot_by_index(request, task_id: str, index: int):
    tr = _get_latest_ui_result_for_task(task_id)
    if tr is None:
        raise Http404()
    _ensure_test_result_screenshot_access(request.user, tr)

    shot = tr.screenshots.filter(step_index=index).first()
    if shot is not None and shot.image:
        abs_path = os.path.realpath(os.path.join(settings.MEDIA_ROOT, shot.image.name))
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        if _path_is_under(abs_path, media_root) and os.path.exists(abs_path):
            return _open_png_response(abs_path)

    safe_root = _playwright_temp_root()
    if tr.temp_dir_path:
        temp_dir = os.path.realpath(tr.temp_dir_path)
        if _path_is_under(temp_dir, safe_root):
            for filename in (f'step_{index}.png', f'step_{index}_fail.png'):
                candidate = os.path.join(temp_dir, 'screenshots', filename)
                if _path_is_under(candidate, temp_dir) and os.path.exists(candidate):
                    return _open_png_response(candidate)

    raise Http404()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_screenshot_media(request, path: str):
    image_name = os.path.normpath(os.path.join('test_screenshots', path)).replace('\\', '/')
    if '..' in image_name.split('/'):
        raise Http404()

    screenshot = get_object_or_404(
        TestScreenshot.objects.select_related(
            'test_result', 'test_result__project', 'test_result__executed_by'
        ),
        image=image_name,
    )
    _ensure_test_result_screenshot_access(request.user, screenshot.test_result)

    abs_path = os.path.realpath(os.path.join(settings.MEDIA_ROOT, screenshot.image.name))
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    if not _path_is_under(abs_path, media_root) or not os.path.exists(abs_path):
        raise Http404()
    return _open_png_response(abs_path)
