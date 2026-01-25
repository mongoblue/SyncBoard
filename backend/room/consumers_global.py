import json
from channels.generic.websocket import AsyncWebsocketConsumer

class GlobalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']

        if self.user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(
            'syetem_boardcast',
            self.channel_name
        )
        await self.accept()
        print("🔔 全局通知服务已连接")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            'system_boardcast',
            self.channel_name
        )

    # 接收来自 View 的消息，转发给前端
    async def global_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event['message'],
            'level': event.get('level', 'info') # info, success, warning
        }))