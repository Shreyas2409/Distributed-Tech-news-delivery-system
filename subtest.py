import time
import json
import random
from locust import HttpUser, task, between, events

class SubscriberUser(HttpUser):
    host = "http://localhost:31100"  
    wait_time = between(1, 3)
    
    def on_start(self):
        self.auth_token = "secret"  
        self.available_topics = ["technology", "local"]
        self.subscribed_topics = set()
    
    @task(3)
    def subscribe_to_topic(self):
      
        if len(self.subscribed_topics) >= len(self.available_topics):
            return
            

        available_to_subscribe = list(set(self.available_topics) - self.subscribed_topics)
        if not available_to_subscribe:
            return
            
        topic = random.choice(available_to_subscribe)
        payload = {"topic": topic}
        
        with self.client.post("/subscribe", 
                              json=payload, 
                              catch_response=True) as response:
            if response.status_code == 200:
                self.subscribed_topics.add(topic)
                response_data = response.json()
                articles = response_data.get("articles", [])
                response.success()
                print(f"Subscribed to '{topic}' and received {len(articles)} articles")
            else:
                response.failure(f"Failed to subscribe: {response.status_code}")
    
    @task(1)
    def unsubscribe_from_topic(self):
        if not self.subscribed_topics:
            return
            
        topic = random.choice(list(self.subscribed_topics))
        payload = {"topic": topic}
        
        with self.client.post("/unsubscribe", 
                              json=payload, 
                              catch_response=True) as response:
            if response.status_code == 200:
                self.subscribed_topics.remove(topic)
                response.success()
                print(f"Unsubscribed from '{topic}'")
            else:
                response.failure(f"Failed to unsubscribe: {response.status_code}")
    
    @task(5)
    def get_news(self):
        with self.client.get("/news", catch_response=True) as response:
            if response.status_code == 200:
                articles = response.json().get("articles", [])
                response.success()
                print(f"Received {len(articles)} news articles")
            else:
                response.failure(f"Failed to get news: {response.status_code}")
