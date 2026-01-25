FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 防止 Python 生成 .pyc 文件
ENV PYTHONDONTWRITEBYTECODE 1
# 实时打印日志到控制台
ENV PYTHONUNBUFFERED 1

# 安装系统依赖 (mysqlclient 需要)
RUN apt-get update && apt-get install -y \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# 确保装了 daphne
RUN pip install daphne 

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令 (使用 Daphne)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]