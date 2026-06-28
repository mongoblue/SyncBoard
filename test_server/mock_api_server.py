"""
Mock API Server - 用于压力测试的目标服务
运行在 5001 端口，提供简单的 API 接口用于压力测试
"""

from flask import Flask, jsonify, request
import time
import random

app = Flask(__name__)


@app.route('/api/health', methods=['GET'])
def health():
    """健康检查接口 - 快速响应"""
    return jsonify({
        "status": "healthy",
        "service": "mock-api-server",
        "timestamp": time.time()
    })


@app.route('/api/users', methods=['GET'])
def get_users():
    """获取用户列表 - 模拟正常业务接口"""
    # 模拟轻微的处理延迟 (10-50ms)
    time.sleep(random.uniform(0.01, 0.05))

    return jsonify({
        "code": 200,
        "data": [
            {"id": 1, "name": "User 1", "email": "user1@example.com"},
            {"id": 2, "name": "User 2", "email": "user2@example.com"},
            {"id": 3, "name": "User 3", "email": "user3@example.com"},
        ],
        "total": 3
    })


@app.route('/api/users', methods=['POST'])
def create_user():
    """创建用户 - 模拟写操作"""
    # 模拟数据库写入延迟 (20-100ms)
    time.sleep(random.uniform(0.02, 0.1))

    data = request.get_json() or {}
    return jsonify({
        "code": 201,
        "message": "User created successfully",
        "data": {
            "id": random.randint(1000, 9999),
            "name": data.get("name", "New User"),
            "email": data.get("email", "user@example.com"),
            "created_at": time.time()
        }
    })


@app.route('/api/products', methods=['GET'])
def get_products():
    """获取产品列表 - 模拟稍微复杂的查询"""
    # 模拟更复杂的查询延迟 (30-150ms)
    time.sleep(random.uniform(0.03, 0.15))

    products = []
    for i in range(1, 11):
        products.append({
            "id": i,
            "name": f"Product {i}",
            "price": round(random.uniform(10, 1000), 2),
            "stock": random.randint(0, 100)
        })

    return jsonify({
        "code": 200,
        "data": products,
        "total": len(products)
    })


@app.route('/api/search', methods=['GET'])
def search():
    """搜索接口 - 模拟计算密集型操作"""
    keyword = request.args.get('q', '')

    # 模拟搜索延迟 (50-200ms)
    time.sleep(random.uniform(0.05, 0.2))

    return jsonify({
        "code": 200,
        "keyword": keyword,
        "results": [
            {"id": i, "title": f"Result {i} for '{keyword}'"}
            for i in range(1, 6)
        ],
        "total": 5
    })


@app.route('/api/slow', methods=['GET'])
def slow_endpoint():
    """慢接口 - 模拟超时场景"""
    # 模拟慢响应 (500ms - 2s)
    delay = random.uniform(0.5, 2.0)
    time.sleep(delay)

    return jsonify({
        "code": 200,
        "message": "Slow response",
        "delay_ms": round(delay * 1000, 2)
    })


@app.route('/api/error', methods=['GET'])
def error_endpoint():
    """错误接口 - 模拟错误场景"""
    # 随机返回错误 (30% 概率)
    if random.random() < 0.3:
        return jsonify({
            "code": 500,
            "error": "Internal Server Error",
            "message": "Something went wrong"
        }), 500

    return jsonify({
        "code": 200,
        "message": "Success (but sometimes fails)"
    })


@app.route('/api/metrics', methods=['GET'])
def metrics():
    """获取服务器指标"""
    return jsonify({
        "status": "running",
        "port": 5001,
        "endpoints": [
            {"path": "/api/health", "method": "GET", "desc": "健康检查"},
            {"path": "/api/users", "method": "GET", "desc": "获取用户列表"},
            {"path": "/api/users", "method": "POST", "desc": "创建用户"},
            {"path": "/api/products", "method": "GET", "desc": "获取产品列表"},
            {"path": "/api/search", "method": "GET", "desc": "搜索"},
            {"path": "/api/slow", "method": "GET", "desc": "慢接口"},
            {"path": "/api/error", "method": "GET", "desc": "错误接口"},
        ]
    })


if __name__ == '__main__':
    print("=" * 50)
    print("Mock API Server 启动中...")
    print("=" * 50)
    print("服务地址: http://127.0.0.1:5001")
    print("测试接口:")
    print("  - GET  http://127.0.0.1:5001/api/health    (健康检查)")
    print("  - GET  http://127.0.0.1:5001/api/users     (用户列表)")
    print("  - POST http://127.0.0.1:5001/api/users     (创建用户)")
    print("  - GET  http://127.0.0.1:5001/api/products  (产品列表)")
    print("  - GET  http://127.0.0.1:5001/api/search    (搜索)")
    print("  - GET  http://127.0.0.1:5001/api/slow      (慢接口)")
    print("  - GET  http://127.0.0.1:5001/api/error     (错误接口)")
    print("=" * 50)

    app.run(
        host='127.0.0.1',
        port=5001,
        debug=False,
        threaded=True  # 启用多线程，支持并发请求
    )
