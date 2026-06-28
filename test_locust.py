from locust import HttpUser, task, between

class TestUser(HttpUser):
    wait_time = between(1, 2)
    
    @task
    def test_api(self):
        self.client.get("http://127.0.0.1:5001/api/users")
