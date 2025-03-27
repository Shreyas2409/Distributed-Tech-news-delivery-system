import pika
import requests
import threading
import time
import random
import json
import os

from flask import Flask, request, jsonify
from newsapi import NewsApiClient

MESSAGE_BROADCAST_NAME = "broadcastExchange"
SECURITY_KEY = os.environ.get("SECURITY_KEY", "secret")

NETWORK_SERVERS = [
    {"identifier": "server1", "endpoint": "http://server1:8080"},
    {"identifier": "server2", "endpoint": "http://server2:8081"},
    {"identifier": "server3", "endpoint": "http://server3:8082"}
]
SERVER_IDENTIFIER = os.environ.get("SERVER_IDENTIFIER", "server1")
REMOTE_SERVERS = [n for n in NETWORK_SERVERS if n["identifier"] != SERVER_IDENTIFIER]

processed_messages_lock = threading.Lock()
article_database_lock = threading.Lock()

processed_messages = set()
article_database = {}
server_status_timestamp = {n["identifier"]: time.time() for n in NETWORK_SERVERS}
active_coordinator = None

app = Flask(__name__)

def attempt_remote_request(endpoint, payload, headers, max_attempts=3, wait_time=1):
    delay = wait_time
    for attempt in range(max_attempts):
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=5)
            return response
        except requests.RequestException as error:
            print(f"[{SERVER_IDENTIFIER}] Request to {endpoint} failed: {error} (attempt {attempt+1})")
            time.sleep(delay)
            delay *= 2
    return None

def select_coordinator():
    global active_coordinator
    current_time = time.time()
    responsive_servers = [server for server in NETWORK_SERVERS if (current_time - server_status_timestamp.get(server["identifier"], 0)) < 15]
    if not responsive_servers:
        new_coordinator = SERVER_IDENTIFIER
    else:
        new_coordinator = sorted(responsive_servers, key=lambda s: s["identifier"])[0]["identifier"]
    if new_coordinator != active_coordinator:
        print(f"[{SERVER_IDENTIFIER}] Coordinator changed: {active_coordinator} -> {new_coordinator}")
    active_coordinator = new_coordinator
    return active_coordinator

def resolve_article_conflict(article_key, incoming_article):
    existing_article = article_database.get(article_key)
    if not existing_article or incoming_article.get("version", 0) > existing_article.get("version", 0):
        article_database[article_key] = incoming_article

@app.route("/consensus", methods=["POST"])
def handle_cluster_messages():
    try:
        provided_token = request.headers.get("X-Auth-Token")
        if provided_token != SECURITY_KEY:
            return jsonify({"error": "Unauthorized"}), 401

        message_data = request.get_json() or {}
        message_type = message_data.get("type")
        if message_type == "heartbeat":
            source_id = message_data.get("node_id", "unknown")
            with threading.Lock():
                server_status_timestamp[source_id] = time.time()
            current = select_coordinator()
            return jsonify({"status": "heartbeat_ack", "current_leader": current}), 200
        else:
            return jsonify({"error": "Unsupported message type"}), 400
    except Exception as error:
        print(f"[{SERVER_IDENTIFIER}] Exception in /consensus: {error}")
        return jsonify({"error": "Internal Server Error"}), 500

class NewsPublisher:
    def __init__(self, server_id, message_broker="rabbitmq"):
        self.server_id = server_id
        self.message_broker = message_broker

        connection_params = pika.ConnectionParameters(
            host=self.message_broker,
            port=5672,
            virtual_host='/',
            credentials=pika.PlainCredentials(
                username=os.environ.get('RABBITMQ_USERNAME', 'guest'),
                password=os.environ.get('RABBITMQ_PASSWORD', 'guest')
            ),
            connection_attempts=int(os.environ.get('RABBITMQ_CONNECTION_ATTEMPTS', 5)),
            retry_delay=int(os.environ.get('RABBITMQ_RETRY_DELAY', 5)),
            socket_timeout=30
        )
        
        self.broker_connection = pika.BlockingConnection(connection_params)
        self.message_channel = self.broker_connection.channel()
        self.message_channel.exchange_declare(exchange=MESSAGE_BROADCAST_NAME, exchange_type='fanout', durable=True)

        self.health_check_thread = threading.Thread(target=self.send_periodic_heartbeats, daemon=True)
        self.health_check_thread.start()

        select_coordinator()
        print(f"[NewsPublisher {self.server_id}] Started. Current coordinator: {active_coordinator}")

    def distribute_news_article(self, article_data, distribution_tag="external"):
        article_key = article_data.get("id")
        if not article_key:
            print(f"[NewsPublisher {self.server_id}] Article missing ID, cannot distribute.")
            return

        if processed_messages_lock.acquire(timeout=3):
            try:
                if article_key not in processed_messages:
                    processed_messages.add(article_key)
                    with article_database_lock:
                        article_database[article_key] = article_data
                else:
                    with article_database_lock:
                        resolve_article_conflict(article_key, article_data)
            finally:
                processed_messages_lock.release()
        else:
            print(f"[NewsPublisher {self.server_id}] Lock acquisition failed for article {article_key}")
            return

        print(
            f"[NewsPublisher {self.server_id}] Distributing article '{article_key}', version={article_data.get('version')}:\n"
            f"  Title: {article_data.get('title')}\n"
            f"  Content: {article_data.get('content')}\n"
            f"  Category: {article_data.get('category')}\n"
        )

        message_body = json.dumps(article_data)
        self.message_channel.basic_publish(
            exchange=MESSAGE_BROADCAST_NAME,
            routing_key=distribution_tag,
            body=message_body,
            properties=pika.BasicProperties(delivery_mode=2)
        )

    def send_periodic_heartbeats(self):
        while True:
            time.sleep(random.uniform(3, 6))
            if not REMOTE_SERVERS:
                continue
            status_update = {
                "type": "heartbeat",
                "node_id": self.server_id
            }
            target_server = random.choice(REMOTE_SERVERS)
            endpoint_url = f"{target_server['endpoint']}/consensus"
            response = attempt_remote_request(endpoint_url, status_update, {"X-Auth-Token": SECURITY_KEY})
            if response is None:
                print(f"[NewsPublisher {self.server_id}] Heartbeat to {target_server['identifier']} failed")
            select_coordinator()

    def shutdown(self):
        if self.broker_connection and self.broker_connection.is_open:
            self.broker_connection.close()

def gather_news_articles(publisher):
    API_ACCESS_KEY = os.environ.get("NEWS_API_KEY", "YOUR-API-KEY")
    news_client = NewsApiClient(api_key=API_ACCESS_KEY)
    retrieval_interval = int(os.environ.get("NEWS_FETCH_INTERVAL", "120"))
    article_version = 100000
    while True:
        time.sleep(retrieval_interval)
        if select_coordinator() == SERVER_IDENTIFIER:
            try:
                api_response = news_client.get_top_headlines(country='us', category='technology')
                if api_response.get("status") == "ok" and api_response.get("articles"):
                    headline = api_response["articles"][0]
                    article_id = f"api-{article_version}"
                    formatted_article = {
                        "id": article_id,
                        "version": article_version,
                        "title": headline.get("title", "No Title"),
                        "content": headline.get("description", "No Content"),
                        "category": "technology"
                    }
                    article_version += 1
                    print(f"[NewsPublisher {SERVER_IDENTIFIER}] Retrieved from API: {formatted_article['title']}")
                    publisher.distribute_news_article(formatted_article, distribution_tag="external")
                else:
                    print(f"[News API] No results or API error.")
            except Exception as error:
                print(f"[News API] Error: {error}")
        else:
            print(f"[News API] Not coordinator, skipping fetch (server={SERVER_IDENTIFIER}).")

def publish_sample_content(publisher):
    predefined_articles = [
        {
            "id": "L-1",
            "version": 1,
            "title": "Breaking News: AI Revolution",
            "content": "Artificial Intelligence is transforming industries worldwide.",
            "category": "technology"
        },
        {
            "id": "L-2",
            "version": 1,
            "title": "Breaking : New Chip released",
            "content": "New chip released.",
            "category": "local"
        },
        {
            "id": "L-3",
            "version": 1,
            "title": "Mobile: New Iphone",
            "content": "New Iphone in design leaked.",
            "category": "local"
        }
    ]
    sequence = 0
    while True:
        time.sleep(15)
        if select_coordinator() == SERVER_IDENTIFIER:
            current_article = predefined_articles[sequence % len(predefined_articles)].copy()
            current_article["version"] += sequence
            current_article["id"] = f"{current_article['id']}-{sequence}"
            print(f"[NewsPublisher {SERVER_IDENTIFIER}] Publishing sample article: {current_article['title']}")
            publisher.distribute_news_article(current_article, distribution_tag="internal")
            sequence += 1

def initialize_system():
    publisher = NewsPublisher(server_id=SERVER_IDENTIFIER, message_broker=os.environ.get("RABBITMQ_HOST", "rabbitmq"))
    api_fetcher = threading.Thread(target=gather_news_articles, args=(publisher,), daemon=True)
    api_fetcher.start()
    sample_publisher = threading.Thread(target=publish_sample_content, args=(publisher,), daemon=True)
    sample_publisher.start()
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        print(f"[NewsPublisher {SERVER_IDENTIFIER}] Shutting down.")
    finally:
        publisher.shutdown()

if __name__ == "__main__":
    from waitress import serve
    publisher_thread = threading.Thread(target=initialize_system, daemon=True)
    publisher_thread.start()
    print(f"[{SERVER_IDENTIFIER} Main] Starting web server on 0.0.0.0:8000 for consensus endpoints")
    serve(app, host="0.0.0.0", port=8000)
