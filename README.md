# Distributed Tech News Delivery System

A scalable, fault-tolerant distributed system for collecting, processing, and delivering technology news to users in real-time using RabbitMQ message broker.

## Project Overview

This project implements a distributed system architecture for tech news delivery that handles high throughput while maintaining low latency. The system collects news from various sources, processes the content, and delivers personalized news feeds to users based on their topic subscriptions.

## Architecture

The system follows a microservices architecture with the following core components:

### 1. Publisher Service
- Collects tech news articles from external API sources and local samples
- Implements a leader election algorithm for coordinator selection 
- Distributes news articles through RabbitMQ's fanout exchange
- Sends periodic heartbeats to maintain cluster health

### 2. Subscriber Service
- Subscribes to RabbitMQ topics to receive relevant news articles
- Maintains a topic registration system for user preferences
- Provides REST API endpoints for client applications
- Implements consensus mechanism for distributed operation

### 3. Messaging System
- Uses RabbitMQ as the message broker with fanout exchange pattern
- Ensures reliable message delivery across distributed components
- Handles article version management and conflict resolution
- Provides fault tolerance through message persistence

## Technologies Used

- **Python**: Core implementation language with Flask for API endpoints
- **RabbitMQ**: Message broker for asynchronous communication between services
- **Docker**: Containerization for deployment
- **Kubernetes**: Orchestration for managing containerized services
- **NewsAPI**: External data source for technology news articles
- **Flask**: Web framework for RESTful API endpoints
- **Waitress**: Production WSGI server for Python applications

## Deployment

### Building Docker Images

```bash
# Build publisher image
docker build -t tech-news-publisher:latest -f dockerfile.publisher2 .

# Build subscriber image
docker build -t tech-news-subscriber:latest -f dockerfile.subscriber2 .

# Tag images (replace yourusername with your Docker Hub username)
docker tag tech-news-publisher:latest yourusername/tech-news-publisher:latest
docker tag tech-news-subscriber:latest yourusername/tech-news-subscriber:latest

# Push images to Docker Hub
docker push yourusername/tech-news-publisher:latest
docker push yourusername/tech-news-subscriber:latest
```

### Kubernetes Deployment

1. Update the image references in the YAML files if needed:
   - Replace `your-dockerdesktop-username/tech-news-publisher:latest` with your image
   - Replace `your-dockerdesktop-username//tech-news-subscriber:latest` with your image

2. Apply the Kubernetes configuration:
   ```bash
   kubectl apply -f tech-news.yaml
   ```

3. Verify deployment:
   ```bash
   kubectl get pods
   kubectl get services
   ```

## API Endpoints

### Publisher Service

- `POST /consensus`: Internal endpoint for cluster coordination
  - Requires `X-Auth-Token` header for authentication
  - Processes heartbeat messages for leader election

### Subscriber Service

- `POST /subscribe`: Subscribe to a news topic
  - Request body: `{"topic": "technology"}`
  - Returns: Confirmation and any existing articles in that topic

- `POST /unsubscribe`: Unsubscribe from a news topic
  - Request body: `{"topic": "technology"}`
  - Returns: Confirmation of unsubscription

- `GET /news`: Retrieve all news articles
  - Returns: JSON array of all available news articles

- `POST /consensus`: Internal endpoint for cluster coordination
  - Requires `X-Auth-Token` header for authentication
  - Processes heartbeat messages

## Testing

### Manual API Testing

```bash
# Subscribe to a topic
curl -v -X POST http://localhost:31100/subscribe \
     -H "Content-Type: application/json" \
     -d '{"topic": "technology"}'

# Unsubscribe from a topic
curl -v -X POST http://localhost:31100/unsubscribe \
     -H "Content-Type: application/json" \
     -d '{"topic": "technology"}'

# Get all news
curl -v http://localhost:31100/news

# Send heartbeat message
curl -v -X POST http://localhost:31100/consensus \
     -H "Content-Type: application/json" \
     -H "X-Auth-Token: secret" \
     -d '{"type": "heartbeat", "node_id": "publisher-1"}'
```

### Load Testing with Locust

1. Install Locust:
   ```bash
   pip install locust
   ```

2. Run publisher load test:
   ```bash
   locust -f pubtest.py
   ```

3. Run subscriber load test:
   ```bash
   locust -f subtest.py
   ```

4. Access the Locust web interface at http://localhost:8089

## System Features

### Fault Tolerance
- Leader election mechanism for coordinating news collection
- Heartbeat monitoring for node health tracking
- Stateful set deployment in Kubernetes for stable network identities

### Data Consistency
- Version-based conflict resolution for news articles
- Atomic operations protected by mutex locks
- Consensus protocol for distributed state management

### Scalability
- Horizontally scalable publisher and subscriber nodes
- RabbitMQ clustering for message broker redundancy
- Kubernetes-based orchestration for auto-scaling

## Dependencies

See `requirements.txt` for the complete list of Python dependencies:
- Flask==2.2.2
- pika==1.3.0
- requests==2.28.1
- newsapi-python==0.2.6
- waitress==2.1.2
- Werkzeug>=2.2.2,<3.0
