from locust import HttpUser, task, between
import json

class PerformanceTestUser(HttpUser):
    """性能测试用户"""
    
    # 等待时间配置
    wait_time = between(0.1, 0.5)
    
    # 请求头
    headers = {}
    
    @task(1)
    def test_endpoint(self):
        """测试目标接口"""
        try:
            self.client.get("http://127.0.0.1:5001/api/users", headers=self.headers)
        except Exception as e:
            print(f"Request failed: {e}")
