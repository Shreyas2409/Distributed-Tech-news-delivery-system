
 1. Building and Pushing Docker Images

Navigate to the directory containing the  Dockerfiles.

 publisher docker Image:

cmd : docker build -t tech-news-publisher:latest -f dockerfile.publisher2 .


subscriber docker image: 
docker build -t tech-news-subscriber:latest -f dockerfile.subscriber2 .


please Replace yourusername  with your Docker Hub username.

For the publisher:
docker tag tech-news-publisher:latest yourusername/tech-news-publisher:latest


For the subscriber:
bash docker tag tech-news-subscriber:latest yourusername/tech-news-subscriber:latest


 Push the Images

For the publisher:

docker push yourusername/tech-news-publisher:latest

For the subscriber:

 docker push yourusername/tech-news-subscriber:latest


2. Deploying on Kubernetes

 Update YAML Files

Replace `shreyashc2409/tech-news-publisher:latest` with `yourusername/tech-news-publisher:latest`
Replace `shreyashc2409/tech-news-subscriber:latest` with `yourusername/tech-news-subscriber:latest`

Deploy the Application

Apply the YAML file to your cluster: kubectl apply -f tech-news.yaml

Check that all pods are running: kubectl get pods

Check that all Services are running: kubectl get services
 

Test endpoints

Subscribe Endpoint

curl -v -X POST http://localhost:31100/subscribe \
     -H "Content-Type: application/json" \
     -d '{"topic": "technology"}'


 Unsubscribe Endpoint

curl -v -X POST http://localhost:31100/unsubscribe \
     -H "Content-Type: application/json" \
     -d '{"topic": "technology"}'


Get News Endpoint - curl -v http://localhost:31100/news


 Consensus Endpoint

curl -v -X POST http://localhost:31100/consensus \
     -H "Content-Type: application/json" \
     -H "X-Auth-Token: secret" \
     -d '{"type": "heartbeat", "node_id": "publisher-1"}'


   







Running Load Tests with Locust:
install locust pip install locust

Run Locust:
locust -f pubtest.py
locust -f subtest.py


