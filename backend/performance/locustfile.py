import os
import time
from locust import HttpUser, task, between
import random
import string

class SyncBoardUser(HttpUser):
    wait_time = between(1, 3)

    def csrf_headers(self):
        csrf_token = self.client.cookies.get("csrftoken")
        if not csrf_token:
            return {}
        token_value = getattr(csrf_token, "value", csrf_token)
        return {"X-CSRFToken": token_value}

    def on_start(self):
        # 1. 登录获取 Token
        self.username = os.environ.get('LOCUST_USERNAME', 'test_user')
        self.password = os.environ.get('LOCUST_PASSWORD', 'password123')
        
        # 登录
        response = self.client.post("/api/auth/login/", json={
            "username": self.username,
            "password": self.password
        })
        
        if response.status_code == 200:
            self.headers = self.csrf_headers()
            if not self.headers:
                print("Login succeeded but csrftoken cookie missing")
                return

            # 创建项目和列
            project_res = self.client.post("/api/projects/", json={
                "name": f"Project {self.username}",
                "description": "Load Testing Project"
            }, headers=self.headers)
            
            if project_res.status_code == 201:
                self.project_id = project_res.json()["id"]
                
                # 获取列 (项目创建时会自动创建默认列)
                column_res = self.client.get(f"/api/columns/?project={self.project_id}", headers=self.headers)
                
                if column_res.status_code == 200:
                    columns = column_res.json()
                    if columns:
                        self.column_id = columns[0]["id"]
                    else:
                        print("No columns found")
                else:
                     print(f"Get columns failed: {column_res.status_code} {column_res.text}")
            else:
                 print(f"Create project failed: {project_res.status_code} {project_res.text}")
        else:
            print(f"Login failed: {response.text}")

    @task(3)
    def create_task(self):
        if not hasattr(self, 'column_id'):
            return
            
        task_title = ''.join(random.choices(string.ascii_letters, k=10))
        self.client.post("/api/tasks/", json={
            "title": f"Task {task_title}",
            "content": "Load testing content",
            "column": self.column_id,
            "position": 0
        }, headers=self.csrf_headers())

    @task(3)
    def search_tasks(self):
        # 模拟搜索任务
        # 我们搜索 "Task" 这个词，因为我们在创建任务时使用了它
        # 注意：Search endpoint 需要我们在 urls.py 里确认
        # 假设是 /api/tasks/search/
        self.client.get("/api/tasks/search/?q=Task", headers=self.headers)

    @task(1)
    def view_board(self):
        # 浏览看板数据（获取项目下列和任务）
        if self.project_id:
            # 获取列
             self.client.get(f"/api/columns/?project={self.project_id}", headers=self.headers)
             # 获取任务
             self.client.get(f"/api/tasks/?project={self.project_id}", headers=self.headers)