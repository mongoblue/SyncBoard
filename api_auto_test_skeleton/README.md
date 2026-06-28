"""
接口自动化测试项目

项目结构：
├── api_auto_test/              # 项目根目录
│   ├── common/                 # 公共封装层
│   │   ├── __init__.py
│   │   ├── api_client.py        # API 请求封装
│   │   ├── assertions.py        # 断言公共方法
│   │   ├── logger.py           # 日志封装
│   │   └── utils.py            # 工具函数
│   │
│   ├── config/                 # 配置层
│   │   ├── __init__.py
│   │   ├── env.py              # 环境配置
│   │   └── settings.py         # 项目设置
│   │
│   ├── data/                   # 测试数据层
│   │   ├── __init__.py
│   │   └── test_data.py       # 测试数据
│   │
│   ├── testcases/             # 测试用例层
│   │   ├── __init__.py
│   │   ├── conftest.py        # 用例级 fixtures
│   │   ├── test_login.py      # 登录模块用例
│   │   └── test_user.py      # 用户模块用例
│   │
│   ├── pytest.ini             # pytest 配置
│   ├── run.py                 # 运行入口
│   └── requirements.txt      # 依赖
"""
