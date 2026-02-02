import threading
import sys
import logging
import subprocess
import os
import re
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction
from faker import Faker
from room.models import Task, Column
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger('django')


# === 1. DataFactoryView (保持不变) ===
class DataFactoryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        column_id = request.data.get('column_id')
        count = int(request.data.get('count', 10))
        clear_old = request.data.get('clear_old', False)
        if not column_id:
            return Response({"error": "缺少 column_id 参数"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            column = Column.objects.get(id=column_id)
        except Column.DoesNotExist:
            return Response({"error": "目标列不存在"}, status=status.HTTP_404_NOT_FOUND)
        fake = Faker('zh_CN')
        tasks_to_create = []
        user = request.user
        try:
            with transaction.atomic():
                if clear_old:
                    Task.objects.filter(column=column).delete()
                for i in range(count):
                    title = fake.sentence(nb_words=6)
                    content = f"{fake.text()}\n\n> 自动生成时间: {fake.date_time()}"
                    tasks_to_create.append(
                        Task(column=column, title=title, content=content, assignee=user, position=65535 + i * 1000))
                Task.objects.bulk_create(tasks_to_create)
            return Response({"msg": f"成功生成 {count} 条测试数据", "column_id": column_id},
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"数据工厂错误: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# === 2. RunTestView (修复了 Locust 逻辑) ===
class RunTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        test_type = request.data.get('test_type', 'api')
        python_exec = sys.executable

        # ✨ 最终逻辑：统一使用 python -m 启动，确保环境一致
        if test_type == 'performance':
            # 1. 性能测试 (Locust)
            cmd = [
                python_exec, "-u", "-m", "locust",
                "-f", "performance/locustfile.py",
                "--headless",
                "--users", "10",
                "--spawn-rate", "2",
                "--run-time", "10s",
                # 👇 关键修复：加上这个参数，不再报 LocustError
                "--host", "http://localhost:8000" 
            ]
        else:
            # 2. 功能测试 (Pytest)
            # 定义基础命令
            base_cmd = [python_exec, "-u", "-m", "pytest"]
            
            # 定义不同类型的路径参数
            paths = {
                'api': ["tests/", "-v"],
                'e2e': ["e2e/", "-v"],
                'default': ["room/tests.py", "-v"],
            }
            # 拼接命令
            args = paths.get(test_type, paths['default'])
            cmd = base_cmd + args

        # 启动流式线程
        thread = threading.Thread(target=self.stream_command_output, args=(cmd,))
        thread.daemon = True
        thread.start()

        return Response({"msg": f"测试已启动: {test_type}"}, status=200)

    def stream_command_output(self, cmd):
        channel_layer = get_channel_layer()
        group_name = "qa_dashboard"
        cwd = settings.BASE_DIR

        # 注入环境变量 (E2E需要)
        env = os.environ.copy()
        env["E2E_BASE_URL"] = "http://frontend"

        self.send_ws(channel_layer, group_name, "test_start", {
            "status": "🚀 START",
            "msg": f"正在执行指令: {' '.join(cmd)}"
        })

        try:
            # 执行命令
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Locust 的日志经常输出在 stderr，合并它！
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # 逐行读取日志
            for line in iter(process.stdout.readline, ''):
                if not line: break
                clean_line = line.strip()

                # 智能进度解析 (兼容 Pytest 和 Locust)
                # 1. Pytest 进度
                if "collected" in clean_line and "items" in clean_line:
                    match = re.search(r'collected (\d+) items', clean_line)
                    if match:
                        total = int(match.group(1))
                        self.send_ws(channel_layer, group_name, "test_meta", {"total": total})

                # 2. Locust 进度 (简单的把 Users 数量当作进度)
                if "Ramping to" in clean_line:
                    self.send_ws(channel_layer, group_name, "test_log", {"log": "🔥 正在启动并发用户..."})

                self.send_ws(channel_layer, group_name, "test_log", {"log": clean_line})

            process.stdout.close()
            return_code = process.wait()

            status_msg = "🏁 测试完成" if return_code == 0 else "❌ 测试失败"
            self.send_ws(channel_layer, group_name, "test_end", {
                "code": return_code,
                "status": status_msg
            })

        except Exception as e:
            logger.error(f"Stream Error: {e}")
            self.send_ws(channel_layer, group_name, "test_end", {
                "code": -1,
                "status": f"💥 异常中断: {e}"
            })

    def send_ws(self, channel_layer, group, msg_type, data):
        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "test_update",
                "message_type": msg_type,
                **data
            }
        )