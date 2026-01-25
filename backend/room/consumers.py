# backend/board/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class BoardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # ✅ 修复 1: 这里的 key 必须和 routing.py 里的 (?P<project_id>...) 保持一致
        self.room_name = self.scope['url_route']['kwargs']['project_id']
        self.room_group_name = f'board_{self.room_name}'
        self.user = self.scope['user']

        # 1. 加入群组
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # 2. 接受连接
        await self.accept()

        # 3. 广播 "用户加入" 消息
        if self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    # ✅ 修复 2: type 必须和下面的方法名 (board_update) 对应！
                    # Channels 会自动把 . 变成 _，所以这里写 'board.update' 或 'board_update' 都可以
                    # 但必须能对应上 method name
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

        # 发送给 WebSocket 前端
        await self.send(text_data=json.dumps({
            # 这里传给前端的数据结构
            # 前端 Board.ts 里 handleSocketMessage 读取的是 payload.data 或 payload
            'data': message,
            'action': message.get('action')  # 方便前端直接读
        }))