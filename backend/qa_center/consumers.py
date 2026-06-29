import json
import re
import asyncio
import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ValidationError
from room.models import Project
from room.project_access import user_can_access_project as _sync_user_can_access_project
from .models import PerformanceTestResult, TestResult, TestRun
from .workers.recorder_supervisor import RecorderSession

logger = logging.getLogger('django')


async def _close_if_anonymous(consumer):
    user = consumer.scope.get('user')
    if not user or not user.is_authenticated:
        await consumer.close(code=4003)
        return True
    return False


async def _discard_group_if_joined(consumer):
    group_name = getattr(consumer, 'group_name', None)
    if group_name:
        await consumer.channel_layer.group_discard(
            group_name,
            consumer.channel_name
        )


@database_sync_to_async
def _user_can_access_project(user, project):
    return _sync_user_can_access_project(user, project)


@database_sync_to_async
def _get_dashboard_project(project_id):
    try:
        return Project.objects.select_related('owner').prefetch_related('members').get(id=project_id)
    except (Project.DoesNotExist, ValueError, TypeError, ValidationError):
        return None


@database_sync_to_async
def _get_test_run_project(run_id):
    try:
        return TestRun.objects.select_related('project__owner').prefetch_related(
            'project__members'
        ).get(id=run_id).project
    except (TestRun.DoesNotExist, ValueError, TypeError, ValidationError):
        return None


@database_sync_to_async
def _get_performance_result_project(execution_id):
    try:
        return PerformanceTestResult.objects.select_related(
            'test_case__project__owner'
        ).prefetch_related(
            'test_case__project__members'
        ).get(test_result_id=execution_id).test_case.project
    except PerformanceTestResult.DoesNotExist:
        return None


@database_sync_to_async
def _get_ui_result_project(task_id):
    try:
        test_result = (
            TestResult.objects.select_related(
                'project__owner',
                'ui_test_case__project__owner',
            )
            .prefetch_related(
                'project__members',
                'ui_test_case__project__members',
            )
            .get(task_id=task_id)
        )
    except (TestResult.DoesNotExist, TestResult.MultipleObjectsReturned, ValueError, TypeError, ValidationError):
        return None

    if test_result.project_id:
        return test_result.project
    if test_result.ui_test_case_id:
        return test_result.ui_test_case.project
    return None


class QAConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if await _close_if_anonymous(self):
            return

        self.project_id = self.scope.get('url_route', {}).get('kwargs', {}).get('project_id')
        if not self.project_id:
            await self.close(code=4003)
            return

        project = await _get_dashboard_project(self.project_id)
        if project is None or not await _user_can_access_project(self.scope['user'], project):
            await self.close(code=4003)
            return
        self.project_id = str(project.id)
        self.group_name = f"qa_dashboard_{project.id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        message = {'type': 'connected'}
        if self.project_id:
            message['project_id'] = str(self.project_id)
        await self.send(text_data=json.dumps(message))

    async def disconnect(self, close_code):
        await _discard_group_if_joined(self)

    # 处理从 conftest.py 发过来的 "test_start" 消息
    async def test_start(self, event):
        await self.send(text_data=json.dumps(event))

    # 处理从 conftest.py 发过来的 "test_update" 消息
    async def test_update(self, event):
        await self.send(text_data=json.dumps(event))

    # 批量执行计划进度（来自 run_plan_executor）
    async def run_plan_progress(self, event):
        await self.send(text_data=json.dumps(event))


class RecorderConsumer(AsyncWebsocketConsumer):
    """UI 测试录制器 WebSocket Consumer（委托给 RecorderSession 子进程）"""

    async def connect(self):
        if await _close_if_anonymous(self):
            return

        self.project_id = self.scope.get('url_route', {}).get('kwargs', {}).get('project_id')
        if self.project_id:
            project = await _get_dashboard_project(self.project_id)
            if project is None or not await _user_can_access_project(self.scope['user'], project):
                await self.close(code=4003)
                return
            self.project_id = str(project.id)

        # 生成简单的组名（channel_name 可能包含特殊字符）
        safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '', self.channel_name[:50])
        self.group_name = f"recorder_{safe_name}"
        self.session: RecorderSession = None

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        message = {
            'type': 'connected',
            'message': '录制器 WebSocket 已连接'
        }
        if self.project_id:
            message['project_id'] = self.project_id
        await self.send(text_data=json.dumps(message))

    async def disconnect(self, close_code):
        session = getattr(self, 'session', None)
        if session:
            session.stop()
            self.session = None

        await _discard_group_if_joined(self)

    async def receive(self, text_data):
        """接收前端消息"""
        try:
            data = json.loads(text_data)
        except Exception:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '无效 JSON'
            }))
            return

        cmd = data.get("command")
        if cmd == "start_recording":
            await self.start(data.get("url", ""), data.get("viewport"))
        elif cmd == "stop_recording":
            await self.stop()
        elif cmd == "pause_recording":
            self.session and self.session.send({"cmd": "pause"})
        elif cmd == "resume_recording":
            self.session and self.session.send({"cmd": "resume"})
        elif cmd == "run_step":
            self.session and self.session.send({"cmd": "run_step", "step": data.get("step") or {}})
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'未知命令: {cmd}'
            }))

    async def start(self, url, viewport):
        if self.session and self.session.is_alive():
            self.session.stop()

        main_loop = asyncio.get_running_loop()

        def on_event(ev):
            mapped = self._map_event(ev)
            if mapped is None:
                return
            asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps(mapped)),
                main_loop,
            )

        self.session = RecorderSession(on_event=on_event)
        self.session.start()
        self.session.send({"cmd": "start", "url": url, "viewport": viewport})

    async def stop(self):
        if not self.session:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '录制未在进行'
            }))
            return
        self.session.stop()
        self.session = None
        await self.send(text_data=json.dumps({
            'type': 'recording_stopped',
            'message': '录制已停止'
        }))

    def _map_event(self, ev):
        # 把 worker 事件映射回前端期望的结构（保留向后兼容）
        t = ev.get("type")
        if t == "ready" and ev.get("success") and "phase" not in ev:
            return {"type": "recording_started", "message": "录制已开始"}
        if t == "error":
            return {
                "type": "error",
                "code": ev.get("code", ""),
                "message": f"[{ev.get('code', '')}] {ev.get('message', '')}",
                "traceback": ev.get("traceback", ""),
            }
        if t == "record_event":
            return {"type": "record_event", "data": ev.get("data")}
        if t == "record_assert_event":
            return {"type": "record_assert_event", "data": ev.get("data")}
        if t == "stopped":
            return {"type": "recording_stopped", "message": "录制已停止"}
        if t == "paused":
            return {"type": "recording_paused"}
        if t == "resumed":
            return {"type": "recording_resumed"}
        if t == "step_run_done":
            return {
                "type": "step_run_done",
                "success": ev.get("success"),
                "code": ev.get("code"),
                "message": ev.get("message"),
            }
        if t == "ready" and "phase" in ev:
            return None
        return ev


class PerformanceTestConsumer(AsyncWebsocketConsumer):
    """性能测试实时数据 WebSocket Consumer"""
    
    async def connect(self):
        if await _close_if_anonymous(self):
            return

        self.execution_id = self.scope['url_route']['kwargs'].get('execution_id')
        project = await _get_performance_result_project(self.execution_id)
        if project is None or not await _user_can_access_project(self.scope['user'], project):
            await self.close(code=4003)
            return

        self.group_name = f"performance_test_{self.execution_id}"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': f'已连接到性能测试 {self.execution_id}'
        }))

    async def disconnect(self, close_code):
        await _discard_group_if_joined(self)

    async def test_update(self, event):
        """接收测试数据更新"""
        await self.send(text_data=json.dumps(event['data']))


class TestRunProgressConsumer(AsyncWebsocketConsumer):
    """TestRun 实时进度推送

    URL: /ws/qa/test-run/{run_id}/
    消息: {type: 'case_done', sequence, status, passed_count, ...}
    """
    async def connect(self):
        if await _close_if_anonymous(self):
            return

        self.run_id = self.scope['url_route']['kwargs'].get('run_id')
        project = await _get_test_run_project(self.run_id)
        if project is None or not await _user_can_access_project(self.scope['user'], project):
            await self.close(code=4003)
            return

        self.group_name = f"test_run_{self.run_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected', 'run_id': self.run_id,
            'message': f'已订阅 TestRun {self.run_id} 的进度',
        }))

    async def disconnect(self, close_code):
        await _discard_group_if_joined(self)

    async def case_done(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def run_finished(self, event):
        await self.send(text_data=json.dumps(event['data']))


class UiRunConsumer(AsyncWebsocketConsumer):
    """UI 用例实时运行进度推送
    URL: /ws/qa/run/{task_id}/
    """
    async def connect(self):
        if await _close_if_anonymous(self):
            return

        self.task_id = self.scope["url_route"]["kwargs"].get("task_id")
        project = await _get_ui_result_project(self.task_id)
        if project is None or not await _user_can_access_project(self.scope['user'], project):
            await self.close(code=4003)
            return

        self.group_name = f"ui_run_{self.task_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected", "task_id": self.task_id}))

    async def disconnect(self, close_code):
        await _discard_group_if_joined(self)

    async def run_event(self, event):
        await self.send(text_data=json.dumps(event["data"]))
