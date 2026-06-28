import json, os, html
import redis
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q
from .models import Project


def _get_redis():
    host = os.getenv('REDIS_HOST', '127.0.0.1')
    return redis.Redis(host=host, port=6379, db=0, decode_responses=True)


def sanitize_html(text):
    if text is None:
        return ''
    return html.escape(str(text), quote=True)


class ChatConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def _is_project_member(self, user, project_id):
        if not user.is_authenticated:
            return False
        return Project.objects.filter(
            Q(id=project_id) & (Q(owner=user) | Q(members=user))
        ).exists()

    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['project_id']
        self.room_group_name = f"chat_{self.room_id}"
        self.stream_key = f"stream:chat:{self.room_id}"
        self.redis = _get_redis()

        # 鉴权: 检查用户是否为项目成员
        if not await self._is_project_member(self.scope['user'], self.room_id):
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # 2. 【关键】连接成功后，立刻读取历史记录发给用户
        # XRANGE: 读取流中的数据，min='-' (最早), max='+' (最新)
        try:
            history = self.redis.xrange(self.stream_key, min='-', max='+')
            history_data = []
            for item in history:
                msg_id, fields = item
                history_data.append({
                    'id': msg_id,
                    'user': fields.get('user'),
                    'content': fields.get('content'),
                    'time': fields.get('time')
                })

            await self.send(text_data=json.dumps({
                'type': 'history',
                'data': history_data
            }))
        except Exception as e:
            print(f"⚠️ Redis 连接失败或读取历史记录错误: {e}")
            # 发送一个空的历史记录，保证前端不报错
            await self.send(text_data=json.dumps({
                'type': 'history',
                'data': []
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 接收前端发来的消息
    async def receive(self, text_data):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4003)
            return

        data = json.loads(text_data)
        message = data.get('message')

        # ✨ 核心修复：不信任前端传来的 user，而是用 session 里的真实用户
        username = self.scope["user"].username

        # Sanitize message content against XSS
        safe_message = sanitize_html(message)
        safe_username = sanitize_html(username)

        # 持久化到 Redis
        msg_id = self.redis.xadd(self.stream_key, {
            'user': safe_username,
            'content': safe_message,
            'time': str(data.get('time', ''))
        })

        # 2. 广播给组内所有人
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'id': msg_id,
                'user': safe_username,
                'content': safe_message,
                'time': data.get('time', '')
            }
        )

    # 处理广播消息
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'data': {
                'id': event['id'],
                'user': event['user'],
                'content': event['content'],
                'time': event['time']
            }
        }))