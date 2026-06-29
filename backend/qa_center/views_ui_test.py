"""
UI 测试用例视图
E2E 自动化测试相关接口
"""

import logging
import threading
import traceback as _tb
import base64
import os
import uuid
from datetime import datetime

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.http import FileResponse, HttpResponseBadRequest, Http404

from .models import UiTestCase, TestResult, TestScreenshot
from .serializers import UiTestCaseSerializer, UiTestCaseListSerializer, UiTestCaseRunSerializer
from .workers import runner_supervisor
from .workers.runner_supervisor import execute_ui_case
from room.project_access import ensure_project_id_access, project_access_q


logger = logging.getLogger("qa_center.runner")


def _playwright_temp_root():
    return os.path.abspath(os.path.join(settings.BASE_DIR, ".playwright-temp"))


def _path_is_under(path, root):
    abs_path = os.path.abspath(path)
    abs_root = os.path.abspath(root)
    try:
        return os.path.commonpath([abs_path, abs_root]) == abs_root
    except ValueError:
        return False


def _ensure_test_result_screenshot_access(user, test_result):
    _ensure_test_result_access(user, test_result, '无权访问该截图')


def _ensure_test_result_access(user, test_result, message='无权访问该测试结果'):
    if test_result.project_id:
        ensure_project_id_access(user, test_result.project_id)
        return
    if test_result.executed_by_id != user.id:
        raise PermissionDenied(message)


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
    return FileResponse(open(path, "rb"), content_type="image/png")


class UiTestCaseViewSet(viewsets.ModelViewSet):
    """UI 测试用例 ViewSet"""

    permission_classes = [IsAuthenticated]
    serializer_class = UiTestCaseSerializer

    def get_queryset(self):
        """根据项目过滤"""
        queryset = UiTestCase.objects.filter(
            project_access_q('project', self.request.user)
        ).distinct()
        project_id = self.request.query_params.get('project')
        if project_id:
            ensure_project_id_access(self.request.user, project_id)
            queryset = queryset.filter(project_id=project_id)
        return queryset.select_related('project', 'created_by')

    def get_object(self):
        """按原始 ID 获取对象后显式校验项目访问权限。"""
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        obj = get_object_or_404(
            UiTestCase.objects.select_related('project', 'created_by'),
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]},
        )
        ensure_project_id_access(self.request.user, obj.project_id)
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        """根据动作选择序列化器"""
        if self.action == 'list':
            return UiTestCaseListSerializer
        return UiTestCaseSerializer

    def perform_create(self, serializer):
        """创建时设置创建者"""
        project = serializer.validated_data.get('project')
        if project:
            ensure_project_id_access(self.request.user, project.id)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """更新时校验目标项目访问权限"""
        project = serializer.validated_data.get('project')
        if project:
            ensure_project_id_access(self.request.user, project.id)
        serializer.save()

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        test_case = self.get_object()
        case_data = {"case_id": test_case.id, "url": test_case.url, "steps": test_case.steps or []}
        events: list = []
        result = execute_ui_case(case_data, on_event=events.append)
        try:
            self._save_test_result(test_case, result, events, request)
        except Exception:
            logger.exception("_save_test_result 失败")
        return Response(self._events_to_payload(events, result), status=status.HTTP_200_OK)

    def _events_to_payload(self, events, result):
        logs = []
        step_screenshots = []
        error_msg = None
        error_code = None
        for ev in events:
            t = ev.get("type")
            if t == "step_log":
                logs.append(ev.get("message", ""))
            elif t == "step_screenshot" and ev.get("path"):
                try:
                    with open(ev["path"], "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    step_screenshots.append({
                        "step": ev.get("index", 0) + 1,
                        "screenshot": f"data:image/png;base64,{b64}",
                    })
                except Exception as exc:
                    logger.warning("读取截图失败: %s (%s)", ev.get("path"), exc)
            elif t == "error":
                error_msg = ev.get("message", "")
                error_code = ev.get("code")
            elif t == "step_done" and not ev.get("success"):
                error_msg = error_msg or ev.get("message", "")
                error_code = error_code or ev.get("code")
        return {
            "success": result.get("success", False),
            "logs": logs,
            "step_screenshots": step_screenshots,
            "error": error_msg,
            "error_code": error_code,
            "summary": result.get("summary", {}),
        }

    def _save_test_result(self, test_case, result, events, request, task_id=None):
        from .models import TestResult, TestScreenshot
        error_msg = ""
        error_code = None
        error_tb = ""
        worker_pid = None
        task_id = task_id or ""
        temp_dir_path = ""
        for ev in events:
            t = ev.get("type")
            if t == "error":
                error_msg = error_msg or ev.get("message", "")
                error_code = error_code or ev.get("code")
                error_tb = error_tb or ev.get("traceback", "")
            elif t == "step_done" and not ev.get("success"):
                error_msg = error_msg or ev.get("message", "")
                error_code = error_code or ev.get("code")
                error_tb = error_tb or ev.get("traceback", "")
            elif t == "supervisor_meta":
                if not task_id:
                    task_id = ev.get("task_id", "") or task_id
                if ev.get("worker_pid") is not None:
                    worker_pid = ev.get("worker_pid")
            elif t == "started":
                temp_dir_path = ev.get("temp_dir", "") or temp_dir_path

        test_result = TestResult.objects.create(
            test_type="ui",
            name=test_case.name,
            project=test_case.project,
            ui_test_case=test_case,
            executed_by=request.user,
            status="passed" if result.get("success") else "failed",
            test_steps=test_case.steps or [],
            actual_result="测试完成" if result.get("success") else error_msg,
            error_message=error_msg,
            task_id=task_id,
            error_code=error_code or "",
            error_traceback=error_tb,
            worker_pid=worker_pid,
            temp_dir_path=temp_dir_path,
            aborted=False,
            test_log="\n".join(ev.get("message", "") for ev in events if ev.get("type") == "step_log"),
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        for ev in events:
            if ev.get("type") == "step_screenshot" and ev.get("path"):
                try:
                    with open(ev["path"], "rb") as f:
                        image_data = f.read()
                    idx = ev.get("index", 0)
                    fname = f"ui_test_step{idx}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"
                    rel_dir = os.path.join("test_screenshots", datetime.now().strftime("%Y/%m/%d"))
                    full_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
                    os.makedirs(full_dir, exist_ok=True)
                    with open(os.path.join(full_dir, fname), "wb") as f:
                        f.write(image_data)
                    TestScreenshot.objects.create(
                        test_result=test_result,
                        name=f"步骤 {idx + 1} 截图",
                        image=os.path.join(rel_dir, fname),
                        step_index=idx,
                    )
                except Exception:
                    logger.exception("保存截图失败")

        # 截图读完后清理 worker 的 temp_dir。worker 已退出，目录所有权归父进程。
        if temp_dir_path and os.path.isdir(temp_dir_path):
            try:
                import shutil
                shutil.rmtree(temp_dir_path, ignore_errors=True)
            except Exception:
                logger.exception("清理 worker temp_dir 失败: %s", temp_dir_path)

        return test_result

    @action(detail=True, methods=['get'], url_path='linked-tasks')
    def linked_tasks(self, request, pk=None):
        test_case = self.get_object()
        tasks = test_case.related_tasks.select_related('column', 'assignee').prefetch_related('tags')
        from room.serializers import TaskSerializer
        return Response(TaskSerializer(tasks, many=True).data)

    @action(detail=False, methods=["post"], url_path=r"runs/(?P<task_id>\w+)/abort")
    def abort_run(self, request, task_id=None):
        """中止一个正在运行的 UI 用例。"""
        if not task_id:
            return Response({"error": "task_id 必填"}, status=status.HTTP_400_BAD_REQUEST)

        tr = _get_authorized_ui_result_for_task(request.user, task_id)

        alive = runner_supervisor.is_runner_alive(task_id)
        if not alive:
            return Response(
                {"task_id": task_id, "aborted": False, "message": "运行已结束或不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )

        ok = runner_supervisor.abort_runner(task_id)
        if not ok:
            return Response(
                {"task_id": task_id, "aborted": False, "message": "终止失败，查看服务端日志"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 标记已存在的 TestResult（如果有）为 aborted
        try:
            if tr.status not in ("passed", "failed"):
                tr.aborted = True
                tr.save(update_fields=["aborted"])
        except Exception:
            logger.exception("标记 TestResult.aborted 失败: %s", task_id)

        return Response({"task_id": task_id, "aborted": True}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path=r"runs/(?P<task_id>\w+)/events")
    def run_events(self, request, task_id=None):
        """返回 task 的历史事件。供前端 WS 晚于 worker 启动时回放。"""
        if not task_id:
            return Response({"error": "task_id 必填"}, status=status.HTTP_400_BAD_REQUEST)
        _get_authorized_ui_result_for_task(request.user, task_id)
        evs = runner_supervisor.get_events(task_id)
        return Response({
            "task_id": task_id,
            "events": evs,
            "finished": any(e.get("type") in ("finished", "run_finished_persisted") for e in evs),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def run_temp(self, request):
        url = request.data.get("url", "")
        steps = request.data.get("steps", [])
        if not url:
            return Response({"error": "请提供起始 URL"}, status=status.HTTP_400_BAD_REQUEST)
        case_data = {"case_id": None, "url": url, "steps": steps}
        events: list = []
        result = execute_ui_case(case_data, on_event=events.append)
        return Response(self._events_to_payload(events, result), status=status.HTTP_200_OK)


def execute_ui_test_cases(case_ids):
    from .workers.runner_supervisor import execute_ui_case
    from .models import TestResult, TestScreenshot
    results = []
    for case_id in case_ids:
        try:
            tc = UiTestCase.objects.get(id=case_id)
        except UiTestCase.DoesNotExist:
            results.append({"case_id": case_id, "case_name": "未知用例", "passed": False, "message": "测试用例不存在"})
            continue
        events: list = []
        result = execute_ui_case(
            {"case_id": tc.id, "url": tc.url, "steps": tc.steps or []},
            on_event=events.append,
        )
        try:
            tr = TestResult.objects.create(
                test_type="ui", name=tc.name, project=tc.project,
                ui_test_case=tc, executed_by=None,
                status="passed" if result.get("success") else "failed",
                test_steps=tc.steps or [],
                actual_result="测试完成" if result.get("success") else "失败",
                error_message="",
                test_log="\n".join(ev.get("message", "") for ev in events if ev.get("type") == "step_log"),
                started_at=timezone.now(), completed_at=timezone.now(),
            )
        except Exception:
            tr = None
        steps_result = []
        for i, step in enumerate(tc.steps or []):
            steps_result.append({
                "step_number": i + 1, "action": step.get("action", ""),
                "selector": step.get("selector", ""), "value": step.get("value", ""),
                "status": "passed" if result.get("success") else "failed", "logs": [],
            })
        results.append({
            "case_id": case_id, "case_name": tc.name, "passed": result.get("success", False),
            "type": "ui",
            "message": "测试完成" if result.get("success") else "失败",
            "request": {"method": "UI", "url": tc.url, "headers": {}, "body": {"steps": tc.steps or []}},
            "response": {"status_code": 200 if result.get("success") else 500, "body": "", "headers": {}},
            "steps": steps_result,
            "screenshot_url": None,
            "assertions": [],
        })
    return results


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ui_run_screenshot(request):
    path = request.query_params.get("path", "")
    task_id = request.query_params.get("task_id", "")
    if not path:
        return HttpResponseBadRequest("path required")
    if not task_id:
        return HttpResponseBadRequest("task_id required")

    tr = _get_latest_ui_result_for_task(task_id)
    if tr is None:
        raise Http404()
    _ensure_test_result_screenshot_access(request.user, tr)

    safe_root = _playwright_temp_root()
    abs_path = os.path.abspath(path)
    temp_dir = os.path.abspath(tr.temp_dir_path) if tr.temp_dir_path else ''
    if not _path_is_under(abs_path, safe_root):
        return HttpResponseBadRequest("invalid path")
    if not temp_dir or not _path_is_under(temp_dir, safe_root) or not _path_is_under(abs_path, temp_dir):
        return HttpResponseBadRequest("invalid path")
    if not os.path.exists(abs_path):
        raise Http404()
    return _open_png_response(abs_path)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ui_run_screenshot_by_index(request, task_id: str, index: int):
    """按 task_id + step_index 读取截图。

    优先尝试最新的 TestResult 关联的 TestScreenshot（持久化副本）；
    若运行尚未结束，回退到该 TestResult 的 temp_dir 中实时读取。
    """
    tr = _get_latest_ui_result_for_task(task_id)
    if tr is None:
        raise Http404()
    _ensure_test_result_screenshot_access(request.user, tr)

    shot = tr.screenshots.filter(step_index=index).first()
    if shot is not None and shot.image:
        abs_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, shot.image.name))
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        if _path_is_under(abs_path, media_root) and os.path.exists(abs_path):
            return _open_png_response(abs_path)

    safe_root = _playwright_temp_root()
    if tr.temp_dir_path:
        temp_dir = os.path.abspath(tr.temp_dir_path)
        if _path_is_under(temp_dir, safe_root):
            for filename in (f"step_{index}.png", f"step_{index}_fail.png"):
                candidate = os.path.join(temp_dir, "screenshots", filename)
                if _path_is_under(candidate, temp_dir) and os.path.exists(candidate):
                    return _open_png_response(candidate)

    raise Http404()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def test_screenshot_media(request, path: str):
    image_name = os.path.normpath(os.path.join('test_screenshots', path)).replace('\\', '/')
    if image_name.startswith('../') or image_name == '..':
        raise Http404()

    screenshot = get_object_or_404(
        TestScreenshot.objects.select_related('test_result', 'test_result__project', 'test_result__executed_by'),
        image=image_name,
    )
    _ensure_test_result_screenshot_access(request.user, screenshot.test_result)

    abs_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, screenshot.image.name))
    media_root = os.path.abspath(settings.MEDIA_ROOT)
    if not _path_is_under(abs_path, media_root) or not os.path.exists(abs_path):
        raise Http404()
    return _open_png_response(abs_path)
