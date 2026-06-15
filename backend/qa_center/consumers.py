import json
import uuid
import re
import asyncio
import threading
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from .utils.recorder import create_recorder, get_recorder, remove_recorder

logger = logging.getLogger('django')


class QAConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 所有打开 QA 面板的用户都加入这个组
        self.group_name = "qa_dashboard"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

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
    """UI 测试录制器 WebSocket Consumer"""
    
    async def connect(self):
        # 生成简单的组名（channel_name 可能包含特殊字符）
        safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '', self.channel_name[:50])
        self.group_name = f"recorder_{safe_name}"
        self.recorder = None
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': '录制器 WebSocket 已连接'
        }))

    async def disconnect(self, close_code):
        # 断开连接时停止录制并清理资源
        if self.recorder:
            self.recorder.stop_recording()
            remove_recorder(self.group_name)
        
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """接收前端消息"""
        try:
            data = json.loads(text_data)
            command = data.get('command')
            
            if command == 'start_recording':
                await self.handle_start_recording(data)
            elif command == 'stop_recording':
                await self.handle_stop_recording()
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'未知命令: {command}'
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '无效的 JSON 数据'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'处理命令失败: {str(e)}'
            }))

    async def handle_start_recording(self, data):
        """处理开始录制命令"""
        url = data.get('url')
        
        if not url:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '缺少 URL 参数'
            }))
            return
        
        # 如果已有录制器在运行，先停止它
        if self.recorder:
            self.recorder.stop_recording()
        
        # 创建新的录制器实例
        self.recorder = create_recorder(self.group_name)
        
        # 获取当前 event loop（必须在主线程中获取）
        main_loop = asyncio.get_event_loop()
        
        # 定义事件回调函数 - 接收录制数据并发送到 WebSocket
        def on_event(event_data):
            logger.info(f"[Consumer] on_event callback called with: {event_data}")
            asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps({
                    'type': 'record_event',
                    'data': event_data
                })),
                main_loop
            )
        
        # 定义就绪回调函数 - 接收浏览器就绪状态
        def on_ready(result):
            logger.info(f"[Consumer] on_ready callback called with: {result}")
            asyncio.run_coroutine_threadsafe(
                self.send(text_data=json.dumps({
                    'type': 'recording_started' if result.get('success') else 'error',
                    'message': result.get('message', '')
                })),
                main_loop
            )
        
        # 启动录制（在新线程中运行阻塞式的录制循环）
        def run_recording():
            try:
                self.recorder.run_recording_loop(url, on_ready, on_event)
            except Exception as e:
                logger.error(f"[Consumer] Recording thread error: {e}")
                asyncio.run_coroutine_threadsafe(
                    self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f'录制线程错误: {str(e)}'
                    })),
                    main_loop
                )
        
        thread = threading.Thread(target=run_recording)
        thread.daemon = True
        thread.start()
        
        await self.send(text_data=json.dumps({
            'type': 'info',
            'message': '正在启动录制...'
        }))

    async def handle_stop_recording(self):
        """处理停止录制命令"""
        if not self.recorder:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '录制未在进行中'
            }))
            return
        
        result = self.recorder.stop_recording()
        remove_recorder(self.group_name)
        self.recorder = None
        
        await self.send(text_data=json.dumps({
            'type': 'recording_stopped',
            'message': result['message']
        }))


class PerformanceTestConsumer(AsyncWebsocketConsumer):
    """性能测试实时数据 WebSocket Consumer"""
    
    async def connect(self):
        self.execution_id = self.scope['url_route']['kwargs'].get('execution_id')
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
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def test_update(self, event):
        """接收测试数据更新"""
        await self.send(text_data=json.dumps(event['data']))


class TestRunProgressConsumer(AsyncWebsocketConsumer):
    """TestRun 实时进度推送

    URL: /ws/qa/test-run/{run_id}/
    消息: {type: 'case_done', sequence, status, passed_count, ...}
    """
    async def connect(self):
        self.run_id = self.scope['url_route']['kwargs'].get('run_id')
        self.group_name = f"test_run_{self.run_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected', 'run_id': self.run_id,
            'message': f'已订阅 TestRun {self.run_id} 的进度',
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def case_done(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def run_finished(self, event):
        await self.send(text_data=json.dumps(event['data']))


class UiRunConsumer(AsyncWebsocketConsumer):
    """UI 用例实时运行进度推送
    URL: /ws/qa/run/{task_id}/
    """
    async def connect(self):
        self.task_id = self.scope["url_route"]["kwargs"].get("task_id")
        self.group_name = f"ui_run_{self.task_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({"type": "connected", "task_id": self.task_id}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def run_event(self, event):
        await self.send(text_data=json.dumps(event["data"]))
