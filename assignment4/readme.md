# Monitoring & Logging Setup with Prometheus and Grafana

This document outlines the steps to set up a comprehensive monitoring and logging system for our Flask application using Prometheus and Grafana on Azure.

## Architecture Overview

The monitoring stack consists of:
1. **Prometheus**: For metrics collection and storage
2. **Grafana**: For visualization and dashboarding
3. **Node Exporter**: For host-level metrics
4. **Alertmanager**: For alert management and notifications
5. **Loki**: For log aggregation (for centralized logging)

## Implementation Steps

### 1. Set Up Azure Virtual Machine for Monitoring

```bash
# Create a dedicated VM for monitoring tools
az vm create \
  --resource-group liaplus-devops-rg \
  --name liaplus-monitoring \
  --image UbuntuLTS \
  --admin-username azureuser \
  --generate-ssh-keys \
  --size Standard_B2s

# Open required ports
az network nsg rule create \
  --resource-group liaplus-devops-rg \
  --nsg-name liaplusmonitoringNSG \
  --name allow-grafana \
  --protocol tcp \
  --priority 1001 \
  --destination-port-range 3000 \
  --access allow

az network nsg rule create \
  --resource-group liaplus-devops-rg \
  --nsg-name liaplusmonitoringNSG \
  --name allow-prometheus \
  --protocol tcp \
  --priority 1002 \
  --destination-port-range 9090 \
  --access allow
```

### 2. Install Docker and Docker Compose

SSH into the VM and install Docker and Docker Compose:

```bash
# Update package lists
sudo apt-get update

# Install prerequisites
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

# Add Docker repository
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce

# Add current user to docker group
sudo usermod -aG docker ${USER}

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### 3. Create Docker Compose Configuration

Create necessary directories and files:

```bash
# Create directories for configuration
mkdir -p prometheus alertmanager grafana/provisioning/datasources grafana/provisioning/dashboards promtail

# Set permissions
chmod -R 777 grafana
```

Create a `docker-compose.yml` file:

```yaml
version: '3'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=15d'
      - '--web.enable-lifecycle'
    ports:
      - "9090:9090"
    networks:
      - monitoring-network

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=securePassword123
      - GF_USERS_ALLOW_SIGN_UP=false
    ports:
      - "3000:3000"
    networks:
      - monitoring-network
    depends_on:
      - prometheus

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    restart: unless-stopped
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($|/)'
    ports:
      - "9100:9100"
    networks:
      - monitoring-network

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    restart: unless-stopped
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"
    networks:
      - monitoring-network

  loki:
    image: grafana/loki:latest
    container_name: loki
    restart: unless-stopped
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
    networks:
      - monitoring-network

  promtail:
    image: grafana/promtail:latest
    container_name: promtail
    restart: unless-stopped
    volumes:
      - ./promtail/promtail-config.yml:/etc/promtail/config.yml
      - /var/log:/var/log
    command: -config.file=/etc/promtail/config.yml
    networks:
      - monitoring-network
    depends_on:
      - loki

networks:
  monitoring-network:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data: