import json
from channels.generic.websocket import AsyncWebsocketConsumer

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