# 使用微软官方 Playwright 镜像
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# 1. 优化系统源（阿里云加速）
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

WORKDIR /app

# 2. 安装编译依赖
# gcc, python3-dev, default-libmysqlclient-dev 是编译 mysqlclient 必须的
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    pkg-config \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 3. 安装 Python 依赖（清华源加速）
# 【关键修改】加上 --break-system-packages 参数，解决 Ubuntu 24.04 禁止 pip 的限制
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 复制代码
COPY . .

# 启动命令
CMD ["uvicorn", "backend.asgi:application", "--host", "0.0.0.0", "--port", "8000"]