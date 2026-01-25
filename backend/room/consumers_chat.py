import json,os
import redis
from channels.generic.websocket import AsyncWebsocketConsumer

# 初始化一个直接连接 Redis 的客户端 (用于操作 Stream)
# 注意：生产环境应该从 settings 获取配置
redis_host = os.getenv('REDIS_HOST', '127.0.0.1')
r = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 从 URL 获取房间号，比如 ws/chat/project_101/
        self.room_id = self.scope['url_route']['kwargs']['project_id']
        self.room_group_name = f"chat_{self.room_id}"
        self.stream_key = f"stream:chat:{self.room_id}"

        # 1. 加入广播组
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # 2. 【关键】连接成功后，立刻读取历史记录发给用户
        # XRANGE: 读取流中的数据，min='-' (最早), max='+' (最新)
        history = r.xrange(self.stream_key, min='-', max='+')

        # 格式化历史记录
        history_data = []
        for item in history:
            # item 结构: (timestamp_id, {field: value})
            msg_id, fields = item
            history_data.append({
                'id': msg_id,
                'user': fields.get('user'),
                'content': fields.get('content'),
                'time': fields.get('time')
            })

        # 发送历史记录给当前用户 (不用广播)
        await self.send(text_data=json.dumps({
            'type': 'history',
            'data': history_data
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 接收前端发来的消息
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message')

        # ✨ 核心修复：不信任前端传来的 user，而是用 session 里的真实用户
        if self.scope["user"].is_authenticated:
            username = self.scope["user"].username
        else:
            username = "Anonymous"  # 或者直接 return 不处理

        # 持久化到 Redis
        msg_id = r.xadd(self.stream_key, {
            'user': username,  # 用真实名字
            'content': message,
            'time': str(data.get('time', ''))
        })

        # 2. 广播给组内所有人
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'id': msg_id,  # Redis 生成的 ID
                'user': username,
                'content': message,
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