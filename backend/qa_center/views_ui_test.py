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
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone

from .models import UiTestCase
from .serializers import UiTestCaseSerializer, UiTestCaseListSerializer, UiTestCaseRunSerializer
from .workers.runner_supervisor import execute_ui_case


logger = logging.getLogger("qa_center.runner")


class UiTestCaseViewSet(viewsets.ModelViewSet):
    """UI 测试用例 ViewSet"""

    permission_classes = [IsAuthenticated]
    serializer_class = UiTestCaseSerializer

    def get_queryset(self):
        """根据项目过滤"""
        queryset = UiTestCase.objects.all()
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset.select_related('created_by')

    def get_serializer_class(self):
        """根据动作选择序列化器"""
        if self.action == 'list':
            return UiTestCaseListSerializer
        return UiTestCaseSerializer

    def perform_create(self, serializer):
        """创建时设置创建者"""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        import uuid as _uuid

        test_case = self.get_object()
        task_id = _uuid.uuid4().hex
        case_data = {"case_id": test_case.id, "url": test_case.url, "steps": test_case.steps or []}

        channel_layer = get_channel_layer()
        group_name = f"ui_run_{task_id}"

        def push(event_data):
            try:
                async_to_sync(channel_layer.group_send)(group_name, {
                    "type": "run_event",
                    "data": event_data,
                })
            except Exception:
                pass

        events: list = []

        def collector(ev):
            events.append(ev)
            push(ev)

        def runner_thread():
            try:
                result = execute_ui_case(case_data, on_event=collector)
                push({"type": "run_finished_persisted", "task_id": task_id})
                self._save_test_result(test_case, result, events, request, task_id=task_id)
            except Exception:
                logger.exception("runner_thread 失败")
                push({"type": "error", "code": "RUNNER_ABORTED",
                      "message": "运行线程异常中止，请查看服务端日志"})
                push({"type": "run_finished_persisted", "task_id": task_id})

        threading.Thread(target=runner_thread, daemon=True).start()

        return Response({"task_id": task_id}, status=status.HTTP_202_ACCEPTED)

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
                        "step": ev.get("index", 0),
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
                        name=f"步骤 {idx} 截图",
                        image=os.path.join(rel_dir, fname),
                    )
                except Exception:
                    logger.exception("保存截图失败")

        return test_result

    @action(detail=True, methods=['get'], url_path='linked-tasks')
    def linked_tasks(self, request, pk=None):
        test_case = self.get_object()
        tasks = test_case.related_tasks.select_related('column', 'assignee').prefetch_related('tags')
        from room.serializers import TaskSerializer
        return Response(TaskSerializer(tasks, many=True).data)

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
