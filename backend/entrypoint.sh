#!/bin/bash

# 1. 循环检查数据库是否就绪
echo "Waiting for MySQL..."
# 这里用 nc (netcat) 命令不停地测试 db 容器的 3306 端口
while ! nc -z db 3306; do
  sleep 0.5
done
echo "MySQL started!"

# 2. 执行数据库迁移
echo "Applying database migrations..."
python manage.py migrate --noinput

# 3. 启动应用
echo "Starting Daphne..."
exec daphne -b 0.0.0.0 -p 8000 backend.asgi:application