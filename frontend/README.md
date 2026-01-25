📂 FlowSpace 项目部署上下文摘要
1. 项目简介 这是一个名为 FlowSpace 的企业级实时协同平台（类似 Trello + Slack）。 目前本地开发环境已全部调通，实现了全栈实时交互。现在需要进行Docker 容器化部署。

2. 技术栈架构

前端: Vue 3 (Composition API) + TypeScript + Vite + Pinia + Element Plus.

后端: Django + DRF + Django Channels (WebSocket).

服务器: Daphne (ASGI 异步服务器，用于处理 WebSocket).

数据库: MySQL 8.0 (持久化存储).

中间件: Redis 7 (负责 Channel Layer 消息分发 + Redis Stream 聊天记录持久化).

3. 项目目录结构 (假设根目录名为 FlowSpace)

Plaintext
FlowSpace/
├── backend/                # Django 后端
│   ├── manage.py
│   ├── requirements.txt    # 依赖：django, channels, daphne, redis, mysqlclient...
│   ├── backend/            # 配置目录 (settings.py, asgi.py, urls.py)
│   └── room/               # 业务 APP (models, consumers, views)
├── frontend/               # Vue 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   └── index.html
└── (待创建) docker-compose.yml
4. 核心功能与路由 (部署时需要 Nginx 转发)

HTTP API: /api/... -> 转发给 Django (8000端口).

WebSocket: /ws/... -> 转发给 Django (8000端口，需支持 Upgrade 头).

/ws/board/ (看板同步)

/ws/global/ (全局通知)

/ws/chat/{room_id}/ (聊天室)

静态资源: / -> 指向 Vue 打包后的 dist 目录 (由 Nginx 直接提供服务).

5. 关键配置现状 (本地 vs 生产)

当前 Settings: DATABASES 和 CHANNEL_LAYERS (Redis) 目前都硬编码指向 127.0.0.1。

部署需求: 需要修改为通过环境变量读取 Docker 服务名（如 db 和 redis）。

启动方式: 目前本地使用 daphne -b 0.0.0.0 -p 8000 backend.asgi:application 启动成功。

6. 下一步目标 我需要编写 Dockerfile (前端和后端) 以及 docker-compose.yml，实现一键启动包含 MySQL + Redis + Django(Daphne) + Nginx(Vue) 的完整环境。

💡 给你的建议
当你去其他对话学习 Docker 时，可以重点关注以下几个问题，这直接关系到这个项目的成败：

多阶段构建 (Multi-stage build)：如何在一个 Dockerfile 里先用 Node 环境打包 Vue，再把生成的文件复制到 Nginx 容器里？（这是前端部署的标准姿势）。

容器互联: Django 容器如何访问 MySQL 容器？（关键词：Service Name, Docker Network, Environment Variables）。

Nginx WebSocket 代理: Nginx 配置里如何写才能支持 WebSocket 的长连接转发？（关键词：Upgrade 和 Connection header）。

ASGI 启动: 为什么 Django Channels 必须用 daphne 或 uvicorn 启动，而不能用普通的 gunicorn 或 runserver？