import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Notification

class GlobalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(
            "system_broadcast",
            self.channel_name
        )
        await self.accept()
        print("🔔 全局通知服务已连接")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            'system_broadcast',
            self.channel_name
        )

    # 接收来自 View 的消息，转发给前端并保存到数据库
    async def global_notification(self, event):
        # 发送给当前连接的客户端
        await self.send(text_data=json.dumps({
            'type': 'global_notification',
            'message': event['message'],
            'level': event.get('level', 'info')  # info, success, warning
        }))
        
        # 保存通知到数据库
        await self.save_notification(event)
    
    @database_sync_to_async
    def save_notification(self, event):
        """保存通知到数据库（批量创建）"""
        try:
            users = User.objects.filter(is_active=True)
            notifications = [
                Notification(
                    user=user,
                    title='系统通知',
                    message=event.get('message', ''),
                    type=event.get('level', 'info'),
                )
                for user in users
            ]
            Notification.objects.bulk_create(notifications, batch_size=500)
        except Exception as e:
            logger = logging.getLogger('django')
            logger.error(f"批量保存通知失败: {e}")