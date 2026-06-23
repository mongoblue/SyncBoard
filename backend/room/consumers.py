"""
看板 BoardConsumer —— 项目看板的实时协作层。

连接时鉴权（is_project_member），加入 group board_{project_id}。
接收前端消息（拖拽、列变更、任务增减）后广播给同项目其他成员。

广播事件格式：
  {action: "refresh", data: ...}    列表刷新
  {action: "column_created", ...}   新列
  {action: "task_moved", ...}       拖拽
  {action: "user_joined/left", ...} 用户进出通知

注意：具体业务数据通过 REST API 写入，WS 仅传递事件通知，客户端收到后调 API 拉最新数据。
"""
# backend/room/consumers.py
import json
import html
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q
from .models import Project


def sanitize_html(text):
    """转义 HTML 特殊字符，防止 XSS 攻击"""
    if text is None:
        return ''
    return html.escape(str(text), quote=True)


class BoardConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def _is_project_member(self, user, project_id):
        """检查用户是否为项目成员"""
        if not user.is_authenticated:
            return False
        return Project.objects.filter(
            Q(id=project_id) & (Q(owner=user) | Q(members=user))
        ).exists()

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['project_id']
        self.room_group_name = f'board_{self.room_name}'
        self.user = self.scope['user']

        # 鉴权: 检查用户是否为项目成员
        if not await self._is_project_member(self.user, self.room_name):
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        if self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'board_update',
                    'message': {
                        'action': 'user_joined',
                        'user': {
                            'id': self.user.id,
                            'username': self.user.username,
                        }
                    }
                }
            )

    async def disconnect(self, close_code):
        # 退出群组
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        # 广播 "用户离开"
        if self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'board_update',  # ✅ 保持一致
                    'message': {
                        'action': 'user_left',
                        'user_id': self.user.id
                    }
                }
            )

    # 接收前端发来的消息 (比如拖拽)
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        # 如果是拖拽等操作，处理完后也需要广播
        if action == 'move_task':
            # ... 你的业务逻辑 ...
            # 广播刷新信号
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'board_update',  # ✅ 保持一致
                    'message': {'action': 'refresh'}
                }
            )

    # ✅ 这个方法名必须和 group_send 里的 'type' 对应
    async def board_update(self, event):
        message = event['message']

        # 安全处理：对所有用户输入进行 HTML 转义
        safe_message = {}
        for key, value in message.items():
            if isinstance(value, str):
                safe_message[key] = sanitize_html(value)
            elif isinstance(value, dict):
                safe_message[key] = {k: sanitize_html(v) if isinstance(v, str) else v for k, v in value.items()}
            elif isinstance(value, list):
                safe_message[key] = [
                    sanitize_html(item) if isinstance(item, str) else item for item in value
                ]
            else:
                safe_message[key] = value

        # 发送给 WebSocket 前端
        await self.send(text_data=json.dumps({
            # 这里传给前端的数据结构
            # 前端 Board.ts 里 handleSocketMessage 读取的是 payload.data 或 payload
            'data': safe_message,
            'action': safe_message.get('action')  # 方便前端直接读
        }))