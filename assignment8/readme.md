# AI Model Deployment with Docker & Kubernetes

This document outlines the process of deploying a sample AI model using Docker and Kubernetes, exposing it via an API endpoint, following MLOps best practices.

## Overview

We'll deploy a simple sentiment analysis model based on TensorFlow, containerize it with Docker, and deploy it to Kubernetes on Azure Kubernetes Service (AKS). The deployment will include proper monitoring, logging, and scaling capabilities.

## Project Structure

```
model-deployment/
├── model/
│   ├── sentiment_model.h5
│   └── tokenizer.pickle
├── src/
│   ├── app.py
│   ├── model_loader.py
│   └── utils.py
├── Dockerfile
├── requirements.txt
├── kubernetes/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   └── hpa.yaml
└── README.md
```

## Application Code

### 1. Model Loading Module (`model_loader.py`)

```python
import os
import pickle
import tensorflow as tf
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences

class SentimentModel:
    def __init__(self):
        model_path = os.environ.get('MODEL_PATH', '/app/model/sentiment_model.h5')
        tokenizer_path = os.environ.get('TOKENIZER_PATH', '/app/model/tokenizer.pickle')
        
        self.max_length = 100  # Maximum sequence length
        
        print("Loading model from:", model_path)
        self.model = load_model(model_path)
        
        print("Loading tokenizer from:", tokenizer_path)
        with open(tokenizer_path, 'rb') as handle:
            self.tokenizer = pickle.load(handle)
    
    def predict(self, text):
        # Tokenize the text
        sequences = self.tokenizer.texts_to_sequences([text])
        # Pad sequences to ensure uniform length
        padded = pad_sequences(sequences, maxlen=self.max_length, padding='post', truncating='post')
        # Make prediction
        prediction = self.model.predict(padded)[0][0]
        sentiment = "positive" if prediction >= 0.5 else "negative"
        
        return {
            "text": text,
            "sentiment": sentiment,
            "confidence": float(prediction if prediction >= 0.5 else 1 - prediction)
        }

# Singleton pattern for model loading
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentimentModel()
    return _model
```

### 2. API Application (`app.py`)

```python
from flask import Flask, request, jsonify
import os
import time
import logging
from prometheus_flask_exporter import PrometheusMetrics
from model_loader import get_model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Add Prometheus metrics
metrics = PrometheusMetrics(app)
metrics.info('app_info', 'Sentiment Analysis API', version='1.0.0')

# Initialize the model (lazy loading)
model = None

@app.before_first_request
def initialize_model():
    global model
    model = get_model()
    logger.info("Model initialized successfully")

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/readiness', methods=['GET'])
def readiness_check():
    global model
    if model is None:
        try:
            model = get_model()
        except Exception as e:
            logger.error(f"Model initialization failed: {str(e)}")
            return jsonify({"status": "not ready", "error": str(e)}), 503
    return jsonify({"status": "ready"}), 200

@app.route('/predict', methods=['POST'])
@metrics.summary('predict_request_latency', 'Time spent processing prediction request')
def predict():
    start_time = time.time()
    
    # Get the request data
    if not request.is_json:
        logger.warning("Request without JSON payload received")
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    
    if 'text' not in data:
        logger.warning("Request missing 'text' field")
        return jsonify({"error": "Missing required field: text"}), 400
    
    text = data['text']
    
    try:
        # Get prediction
        result = model.predict(text)
        
        # Log the prediction (exclude the actual text for privacy)
        logger.info(f"Prediction made: sentiment={result['sentiment']}, "
                   f"confidence={result['confidence']:.4f}, "
                   f"processing_time={time.time()-start_time:.4f}s")
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/batch-predict', methods=['POST'])
@metrics.summary('batch_predict_request_latency', 'Time spent processing batch prediction request')
def batch_predict():
    # Get the request data
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    
    if 'texts' not in data or not isinstance(data['texts'], list):
        return jsonify({"error": "Missing required field: texts (must be an array)"}), 400
    
    texts = data['texts']
    
    try:
        # Get predictions for each text
        results = [model.predict(text) for text in texts]
        return jsonify({"predictions": results}), 200
    
    except Exception as e:
        logger.error(f"Batch prediction error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Get port from environment or default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
```

### 3. Requirements File (`requirements.txt`)

```
flask==2.0.1
tensorflow==2.6.0
numpy==1.19.5
gunicorn==20.1.0
prometheus-flask-exporter==0.18.2
pyyaml==5.4.1
```

## Docker Configuration

### Dockerfile

```dockerfile
FROM python:3.8-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY model/ ./model/

# Set Python path
ENV PYTHONPATH=/app

# Set health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-5000}/health || exit 1

# Run with Gunicorn
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 60 "src.app:app"
```

## Kubernetes Configuration

### 1. Deployment YAML (`kubernetes/deployment.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sentiment-model
  labels:
    app: sentiment-model
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sentiment-model
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: sentiment-model
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: /metrics
        prometheus.io/port: "5000"
    spec:
      containers:
      - name: sentiment-model
        image: ${DOCKER_REGISTRY}/sentiment-model:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 5000
        env:
        - name: PORT
          value: "5000"
        - name: MODEL_PATH
          value: "/app/model/sentiment_model.h5"
        - name: TOKENIZER_PATH
          value: "/app/model/tokenizer.pickle"
        - name: LOG_LEVEL
          valueFrom:
            configMapKeyRef:
              name: model-config
              key: log_level
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2"
            memory: "4Gi"
        readinessProbe:
          httpGet:
            path: /readiness
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 60
          periodSeconds: 15
          timeoutSeconds: 5
        volumeMounts:
        - name: model-volume
          mountPath: /app/model
      volumes:
      - name: model-volume
        persistentVolumeClaim:
          claimName: model-pvc
```

### 2. Service YAML (`kubernetes/service.yaml`)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sentiment-model-service
  labels:
    app: sentiment-model
spec:
  selector:
    app: sentiment-model
  ports:
  - port: 80
    targetPort: 5000
    protocol: TCP
  type: ClusterIP
```

### 3. Ingress YAML (`kubernetes/ingress.yaml`)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sentiment-model-ingress
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - api.model.liaplus.com
    secretName: model-tls-secret
  rules:
  - host: api.model.liaplus.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: sentiment-model-service
            port:
              number: 80
```

### 4. ConfigMap YAML (`kubernetes/configmap.yaml`)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: model-config
data:
  log_level: "INFO"
  batch_size: "32"
```

### 5. Horizontal Pod Autoscaler (`kubernetes/hpa.yaml`)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: sentiment-model-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sentiment-model
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 60
```

### 6. Persistent Volume Claim (`kubernetes/pvc.yaml`)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: model-pvc
spec:
  accessModes:
    - ReadOnlyMany
  resources:
    requests:
      storage: 1Gi
  storageClassName: azurefile
```

## Deployment Steps

### 1. Build and Push Docker Image

```bash
# Set variables
DOCKER_REGISTRY="yourregistry.azurecr.io"
IMAGE_NAME="sentiment-model"
IMAGE_TAG="latest"

# Build the Docker image
docker build -t ${DOCKER_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} .

# Log in to Azure Container Registry
az acr login --name yourregistry

# Push the image to the registry
docker push ${DOCKER_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}
```

### 2. Create Azure Kubernetes Service (AKS) Cluster

```bash
# Create resource group
az group create --name liaplus-mlops-rg --location eastus

# Create AKS cluster
az aks create \
  --resource-group liaplus-mlops-rg \
  --name liaplus-aks \
  --node-count 3 \
  --enable-addons monitoring \
  --generate-ssh-keys \
  --node-vm-size Standard_DS3_v2 \
  --network-plugin azure \
  --enable-cluster-autoscaler \
  --min-count 3 \
  --max-count 6

# Connect to the AKS cluster
az aks get-credentials --resource-group liaplus-mlops-rg --name liaplus-aks

# Verify connection
kubectl get nodes
```

### 3. Create Storage for Model Files

```bash
# Create persistent volume claim
kubectl apply -f kubernetes/pvc.yaml

# Copy model files to the persistent volume
# (This is typically done through a CI/CD pipeline or init container)
kubectl cp ./model pod-name:/app/model
```

### 4. Apply Kubernetes Configurations

```bash
# Create namespace
kubectl create namespace ml-models

# Set current namespace
kubectl config set-context --current --namespace=ml-models

# Apply ConfigMap
kubectl apply -f kubernetes/configmap.yaml

# Apply Deployment
# First, update the deployment.yaml with the correct registry
sed -i "s|\${DOCKER_REGISTRY}|${DOCKER_REGISTRY}|g" kubernetes/deployment.yaml
kubectl apply -f kubernetes/deployment.yaml

# Apply Service
kubectl apply -f kubernetes/service.yaml

# Apply HPA
kubectl apply -f kubernetes/hpa.yaml

# Apply Ingress
kubectl apply -f kubernetes/ingress.yaml
```

### 5. Verify Deployment

```bash
# Check if pods are running
kubectl get pods

# Check logs
kubectl logs deployment/sentiment-model

# Check the service
kubectl get svc sentiment-model-service

# Test the API
curl -X POST \
  https://api.model.liaplus.com/predict \
  -H 'Content-Type: application/json' \
  -d '{"text": "I really enjoyed using this product, it was amazing!"}'
```

## MLOps Best Practices Implemented

### 1. Containerization
- Docker encapsulates the model and its dependencies
- Ensures consistency across development and production environments
- Enables reproducible deployments

### 2. Infrastructure as Code (IaC)
- Kubernetes manifests define the entire infrastructure
- Version-controlled configuration
- Repeatable deployments

### 3. Health Monitoring
- Readiness probes ensure the model is fully loaded before serving traffic
- Liveness probes detect and recover from application failures
- Prometheus metrics for performance monitoring

### 4. Auto-scaling
- Horizontal Pod Autoscaler adjusts replicas based on demand
- Resource requests and limits prevent resource starvation
- Scale up quickly, scale down conservatively to handle traffic spikes

### 5. CI/CD Integration
- Automated build and deployment process
- Version tagging for model traceability
- Canary deployments for risk mitigation

### 6. Logging and Monitoring
- Structured logging for easier analysis
- Performance metrics collection with Prometheus
- Latency tracking for API requests

## Extensions for Production Use

### 1. Model Versioning and Serving

```yaml
# Using Kubernetes deployments for different model versions
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sentiment-model-v2
  labels:
    app: sentiment-model
    version: v2
spec:
  # Similar to main deployment but with version-specific settings
```

### 2. A/B Testing Configuration

```yaml
# Service for traffic splitting
apiVersion: v1
kind: Service
metadata:
  name: sentiment-model-service
spec:
  selector:
    app: sentiment-model
  ports:
  - port: 80
    targetPort: 5000
  # No specific version in selector to allow routing to multiple versions

---
# Virtual Service for traffic splitting (with Istio)
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: sentiment-model-vsvc
spec:
  hosts:
  - api.model.liaplus.com
  http:
  - route:
    - destination:
        host: sentiment-model-service
        subset: v1
      weight: 90
    - destination:
        host: sentiment-model-service
        subset: v2
      weight: 10
```

### 3. Model Monitoring and Drift Detection

```python
# Add to app.py for monitoring prediction distributions
from prometheus_client import Histogram

PREDICTION_HISTOGRAM = Histogram(
    'model_prediction_value', 
    'Distribution of model predictions',
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# In the predict function
def predict():
    # ... existing code ...
    
    # Record prediction for monitoring
    PREDICTION_HISTOGRAM.observe(result['confidence'])
    
    # ... rest of function ...
```

### 4. Automated Model Retraining Pipeline

```yaml
# Kubernetes CronJob for scheduled model retraining
apiVersion: batch/v1
kind: CronJob
metadata:
  name: model-retraining
spec:
  schedule: "0 0 * * 0"  # Weekly on Sunday at midnight
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: model-training
            image: yourregistry.azurecr.io/model-training:latest
            env:
            - name: DATA_SOURCE
              value: "azure-storage://training-data/sentiment"
            - name: MODEL_OUTPUT
              value: "azure-storage://models/sentiment/new"
          restartPolicy: OnFailure
```


## Conclusion

This implementation demonstrates a production-ready MLOps deployment for a sentiment analysis model using Docker and Kubernetes on Azure. The deployment follows best practices for containerization, orchestration, monitoring, and scaling, ensuring that the model can be reliably served in a production environment.

The solution can be extended with additional MLOps practices like model versioning, A/B testing, and automated retraining pipelines as the project matures. By leveraging Kubernetes' declarative configuration and scaling capabilities, the model service can handle varying loads while maintaining performance and reliability.