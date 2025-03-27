#!/usr/bin/env python3
import pika
import requests
import threading
import time
import random
import json
import os

from flask import Flask, request, jsonify

MESSAGE_BROADCAST_NAME = "broadcastExchange"
SECURITY_CREDENTIAL = os.environ.get("AUTH_TOKEN", "secret")

NETWORK_SERVERS = [
    {"id": "node1", "url": "http://subscriber1:8090"},
    {"id": "node2", "url": "http://subscriber2:8091"},
    {"id": "node3", "url": "http://subscriber3:8092"}
]
CURRENT_PARTICIPANT_ID = os.environ.get("NODE_ID", "node1")
REMOTE_PARTICIPANTS = [node for node in NETWORK_SERVERS if node["id"] != CURRENT_PARTICIPANT_ID]

processed_entries_mutex = threading.Lock()
content_database_mutex = threading.Lock()
topic_registrations_mutex = threading.Lock()
keepalive_mutex = threading.Lock()

processed_entries = set()
content_database = {}
last_keepalive_timestamp = {node["id"]: time.time() for node in NETWORK_SERVERS}

topic_registrations = set()

app = Flask(__name__)

def apply_update_strategy(entry_id, updated_entry):
    existing_entry = content_database.get(entry_id)
    if not existing_entry or updated_entry.get("version", 0) > existing_entry.get("version", 0):
        content_database[entry_id] = updated_entry

@app.route("/subscribe", methods=["POST"])
def register_topic_interest():
    request_data = request.get_json() or {}
    requested_topic = request_data.get("topic")
    if not requested_topic:
        return jsonify({"error": "No topic provided"}), 400

    with topic_registrations_mutex:
        topic_registrations.add(requested_topic)
    print(f"[{CURRENT_PARTICIPANT_ID}] Subscribed to topic '{requested_topic}'")
    
    with content_database_mutex:
        relevant_entries = [entry for entry in content_database.values() if entry.get("category") == requested_topic]
    return jsonify({"status": "subscribed", "topic": requested_topic, "articles": relevant_entries}), 200

@app.route("/unsubscribe", methods=["POST"])
def remove_topic_interest():
    request_data = request.get_json() or {}
    target_topic = request_data.get("topic")
    if not target_topic:
        return jsonify({"error": "No topic provided"}), 400

    with topic_registrations_mutex:
        if target_topic in topic_registrations:
            topic_registrations.remove(target_topic)
            print(f"[{CURRENT_PARTICIPANT_ID}] Unsubscribed from topic '{target_topic}'")
            return jsonify({"status": "unsubscribed", "topic": target_topic}), 200
        else:
            return jsonify({"error": f"Not subscribed to topic '{target_topic}'"}), 400

@app.route("/news", methods=["GET"])
def retrieve_all_content():
    with content_database_mutex:
        all_entries = list(content_database.values())
    return jsonify({"articles": all_entries}), 200

@app.route("/consensus", methods=["POST"])
def process_network_message():
    try:
        provided_token = request.headers.get("X-Auth-Token")
        if provided_token != SECURITY_CREDENTIAL:
            return jsonify({"error": "Unauthorized"}), 401

        message_data = request.get_json() or {}
        message_category = message_data.get("type")
        if message_category == "heartbeat":
            origin_id = message_data.get("node_id", "unknown")
            with keepalive_mutex:
                last_keepalive_timestamp[origin_id] = time.time()
            return jsonify({"status": "heartbeat_ack"}), 200
        else:
            return jsonify({"error": "Unsupported message type"}), 400
    except Exception as error:
        print(f"[{CURRENT_PARTICIPANT_ID}] Exception in /consensus: {error}")
        return jsonify({"error": "Internal Server Error"}), 500

class ContentReceiver:
    def __init__(self, participant_id, message_broker="rabbitmq"):
        self.participant_id = participant_id
        self.message_broker_host = message_broker

        connection_params = pika.ConnectionParameters(
            host=self.message_broker_host,
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

        queue_result = self.message_channel.queue_declare(queue="", exclusive=True)
        self.assigned_queue = queue_result.method.queue
        self.message_channel.queue_bind(exchange=MESSAGE_BROADCAST_NAME, queue=self.assigned_queue)

        self.message_processor_thread = threading.Thread(target=self.begin_message_processing, daemon=True)
        self.message_processor_thread.start()

        self.network_coordination_thread = threading.Thread(target=self.maintain_network_presence, daemon=True)
        self.network_coordination_thread.start()

        print(f"[ContentReceiver {self.participant_id}] Initialized, queue={self.assigned_queue}")

    def begin_message_processing(self):
        def handle_message(channel, method, properties, body):
            try:
                entry_data = json.loads(body)
            except json.JSONDecodeError:
                print(f"[{self.participant_id}] Received invalid JSON.")
                return
            entry_id = entry_data.get("id")
            if not entry_id:
                return
            entry_category = entry_data.get("category")
            with topic_registrations_mutex:
                if entry_category and entry_category not in topic_registrations:
                    print(f"[{self.participant_id}] RabbitMQ => Article '{entry_id}' (category='{entry_category}') IGNORED (not subscribed).")
                    return
            with processed_entries_mutex:
                if entry_id not in processed_entries:
                    processed_entries.add(entry_id)
                    with content_database_mutex:
                        content_database[entry_id] = entry_data
                    print(
                        f"[ContentReceiver {self.participant_id}] RabbitMQ => NEW article '{entry_id}', version={entry_data.get('version')}:\n"
                        f"  Title: {entry_data.get('title')}\n"
                        f"  Content: {entry_data.get('content')}\n"
                        f"  Category: {entry_category}\n"
                    )
                else:
                    with content_database_mutex:
                        previous_version = content_database.get(entry_id)
                        apply_update_strategy(entry_id, entry_data)
                        if content_database[entry_id] != previous_version:
                            print(
                                f"[ContentReceiver {self.participant_id}] RabbitMQ => UPDATED article '{entry_id}', version={entry_data.get('version')}:\n"
                                f"  Title: {entry_data.get('title')}\n"
                                f"  Content: {entry_data.get('content')}\n"
                                f"  Category: {entry_category}\n"
                            )
        self.message_channel.basic_consume(queue=self.assigned_queue, on_message_callback=handle_message, auto_ack=True)
        self.message_channel.start_consuming()

    def maintain_network_presence(self):
        while True:
            time.sleep(random.uniform(5, 10))
            if not REMOTE_PARTICIPANTS:
                continue
            status_update = {
                "type": "heartbeat",
                "node_id": self.participant_id
            }
            target_peer = random.choice(REMOTE_PARTICIPANTS)
            try:
                requests.post(
                    f"{target_peer['url']}/consensus",
                    json=status_update,
                    headers={"X-Auth-Token": SECURITY_CREDENTIAL},
                    timeout=5
                )
            except requests.RequestException:
                pass

    def shutdown(self):
        if self.broker_connection and self.broker_connection.is_open:
            self.broker_connection.close()

def run_service():
    content_receiver = ContentReceiver(participant_id=CURRENT_PARTICIPANT_ID, message_broker=os.environ.get("RABBITMQ_HOST", "rabbitmq"))
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        print(f"[ContentReceiver {CURRENT_PARTICIPANT_ID}] Exiting main loop.")
    finally:
        content_receiver.shutdown()

if __name__ == "__main__":
    from waitress import serve
    background_thread = threading.Thread(target=run_service, daemon=True)
    background_thread.start()
    print(f"[{CURRENT_PARTICIPANT_ID} Main] Serving Flask on 0.0.0.0:8001 (subscribe/unsubscribe, /consensus, /news)")
    serve(app, host="0.0.0.0", port=8001)