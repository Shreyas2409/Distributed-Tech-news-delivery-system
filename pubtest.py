import time
import json
import random
from locust import HttpUser, task, between, events

class PublisherUser(HttpUser):
    host = "http://localhost:31010"  
    wait_time = between(1, 5)
    
    def on_start(self):
        self.auth_token = "secret"  
    
    @task(1)
    def send_heartbeat(self):
        """Simulates heartbeat messages sent to consensus endpoint"""
        node_id = f"test-server-{random.randint(1, 100)}"
        payload = {
            "type": "heartbeat",
            "node_id": node_id
        }
        headers = {"X-Auth-Token": self.auth_token}
        
        with self.client.post("/consensus", 
                              json=payload, 
                              headers=headers, 
                              catch_response=True) as response:
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("status") == "heartbeat_ack":
                    response.success()
                else:
                    response.failure(f"Expected 'heartbeat_ack' status, got: {response_data}")
            else:
                response.failure(f"Status code: {response.status_code}")