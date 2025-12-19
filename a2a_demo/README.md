# A2A Multi-Agent OpenShift Demo

This demo showcases a multi-agent system that automatically diagnoses and remediates microservice performance issues in OpenShift using LLM-powered agents.

## Demo Scenario

A cascading performance problem occurs:
1. **Microservice A** (Queue Service) receives client requests and queues them
2. **Microservice B** (Processing Service) has intentionally low CPU limits (25m)
3. Queue depth builds up as Microservice B can't keep up
4. **Prometheus** fires `HighQueueDepth` alert when queue > 10
5. **Alertmanager** sends webhook to **Agent 1**
6. **Agent 1** collects Microservice A metrics, analyzes with LLM, identifies Microservice B as bottleneck
7. **Agent 1** sends diagnosis to **Agent 2**
8. **Agent 2** collects deployment configs and metrics for both services, analyzes with LLM
9. **Agent 2** generates and executes `oc` commands to increase Microservice B CPU limits
10. System recovers, alert resolves

## Architecture

```
┌─────────┐       ┌────────────────┐       ┌────────────────┐
│ Client  │──────>│ Microservice A │──────>│ Microservice B │
│Simulator│       │ (Queue Service)│       │(Processing Svc)│
└─────────┘       │                │       │                │
                  │ Queue Depth    │       │ CPU-Intensive  │
                  │ Monitoring     │       │ Low CPU Limit  │
                  └────────┬───────┘       └────────┬───────┘
                           │                        │
                           └────────┬───────────────┘
                                    │
                           ┌────────▼────────┐
                           │   Prometheus    │
                           │   Monitoring    │
                           └────────┬────────┘
                                    │
                           ┌────────▼────────┐
                           │  Alertmanager   │
                           │   (Webhook)     │
                           └────────┬────────┘
                                    │
                           ┌────────▼────────┐
                           │    Agent 1      │
                           │  (Diagnose)     │
                           │   LLM: Llama    │
                           └────────┬────────┘
                                    │
                           ┌────────▼────────┐
                           │    Agent 2      │
                           │  (Remediate)    │
                           │   LLM: Llama    │
                           └─────────────────┘
```

## Components

### Microservices

**Microservice A (Queue Service)**
- Flask service with internal message queue (max size: 100)
- Calls Microservice B for processing
- Exposes metrics: `queue_service_queue_depth`, latency to B, request rates
- **Access**: Agent 1 can query these metrics

**Microservice B (Processing Service)**
- Flask service with CPU-intensive workload (computes prime numbers)
- **Intentionally bottlenecked** with low CPU limit (25m)
- Exposes metrics: CPU usage, processing duration, active requests
- **Access**: Agent 2 can query these metrics and deployment config

**Client Simulator**
- Sends continuous requests to Microservice A (default: 2 req/sec)

### Agents

**Agent 1 (DiagnoseAgent)** - [agent1.py](agent1/agent1.py)
- Receives `HighQueueDepth` alerts via webhook from Alertmanager
- **Access**: Can only query Microservice A metrics (queue depth, latency to B)
- **Cannot access**: Microservice B metrics or deployment details
- Analyzes data with LLM (Llama 3.1 8B)
- Identifies which microservice is the bottleneck based on queue + latency patterns
- Sends diagnosis to Agent 2 via HTTP POST
- **Framework**: A2A protocol, FastAPI

**Agent 2 (RemediateAgent)** - [agent2.py](agent2/agent2.py)
- Receives diagnosis from Agent 1
- **Access**: Can query both Microservice A and B deployment configs and metrics
- Collects CPU/memory metrics and resource limits for both services
- Analyzes with LLM to correlate symptoms with resource limits
- Generates `oc set resources` commands to fix the issue
- Executes commands to patch deployments
- **Framework**: A2A protocol, FastAPI

### Monitoring

**Prometheus**
- Scrapes metrics from both microservices
- Evaluates alert rules

**Alertmanager**
- Auto-configured via Helm (`AlertmanagerConfig` CRD)
- Sends webhooks to Agent 1 when `HighQueueDepth` fires

## Quick Start

### 1. Build Container Images

```bash
cd a2a_demo
chmod +x build-images.sh
./build-images.sh
```

Builds images:
- `microservice-a:latest`
- `microservice-b:latest`
- `client-simulator:latest`
- `agent1:latest`
- `agent2:latest`

### 2. Push to Registry

```bash
# Login to OpenShift registry
podman login -u <user> -p <password> <registry-url>

# Build and push all images
./build-images.sh --all
```

### 3. Deploy to OpenShift

```bash
chmod +x deploy.sh
./deploy.sh a2a-demo
```

This deploys via Helm with Alertmanager integration enabled.

### 4. Verify Deployment

```bash
# Check pods
oc get pods -n a2a-demo

# Expected output:
# NAME                                READY   STATUS    RESTARTS   AGE
# microservice-a-xxxxxxxxxx-xxxxx     1/1     Running   0          1m
# microservice-b-xxxxxxxxxx-xxxxx     1/1     Running   0          1m
# client-simulator-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
# agent1-xxxxxxxxxx-xxxxx             1/1     Running   0          1m
# agent2-xxxxxxxxxx-xxxxx             1/1     Running   0          1m

# Watch the demo in action
oc logs -f deployment/agent1 -n a2a-demo  # See Agent 1 diagnosis
oc logs -f deployment/agent2 -n a2a-demo  # See Agent 2 remediation
```

### 5. Watch the Demo

After deployment, the queue will build up and trigger the alert within ~1-2 minutes:

```bash
# Watch Agent 1 receive alert and diagnose
oc logs -f deployment/agent1 -n a2a-demo
# You'll see:
# 📥 Webhook received: status=firing, alerts=1
# 📊 Collecting diagnostic data...
# 🤖 Analyzing with LLM...
# 🔍 AGENT 1 DIAGNOSIS: Microservice B is the bottleneck...
# 📤 Calling Agent 2...

# Watch Agent 2 remediate
oc logs -f deployment/agent2 -n a2a-demo
# You'll see:
# 📥 Remediation request received
# 📋 Collecting deployment configurations...
# 📊 Collecting system metrics...
# 🤖 Analyzing with LLM...
# 🔧 Executing remediation command(s)...
# ✅ AGENT 2 REMEDIATION COMPLETE!
```

## Configuration

### Helm Values

Edit [helm/a2a-demo/values.yaml](helm/a2a-demo/values.yaml):

```yaml
# Microservice B - Adjust CPU to control bottleneck severity
microserviceB:
  resources:
    limits:
      cpu: "25m"  # Very low = severe bottleneck

# Client load
client:
  env:
    requestRate: "2.0"  # Requests per second

# Prometheus & Alertmanager
prometheus:
  enabled: true
  alertmanager:
    enabled: true  # Auto-configures webhook to Agent 1
  alertRules:
    queueDepthThreshold: 10  # Alert fires when queue > 10
```

### Environment Variables

**Agent 1**:
- `LLM_ENDPOINT`: LLM service URL
- `PROMETHEUS_URL`: Prometheus URL (default: thanos-querier)
- `MICROSERVICE_A_URL`: Microservice A endpoint
- `AGENT2_URL`: Agent 2 endpoint

**Agent 2**:
- `LLM_ENDPOINT`: LLM service URL
- `PROMETHEUS_URL`: Prometheus URL
- `NAMESPACE`: Target namespace (default: a2a-demo)
- `MICROSERVICE_A_DEPLOYMENT`: Deployment name
- `MICROSERVICE_B_DEPLOYMENT`: Deployment name

## Key Metrics

### Microservice A
- `queue_service_queue_depth` - Current queue depth ⚠️ **Triggers alert > 10**
- `queue_service_requests_total` - Total requests received
- `queue_service_microservice_b_latency_seconds` - Latency to B

### Microservice B
- `processing_service_requests_total` - Requests processed
- `processing_service_processing_duration_seconds` - Processing time
- `process_cpu_seconds_total` - CPU usage
- `process_resident_memory_bytes` - Memory usage

## Agent Workflow

### Agent 1 Workflow
1. Receive webhook from Alertmanager (`POST /webhook`)
2. Extract alert details (name, labels, annotations)
3. Collect metrics from Microservice A:
   - Queue depth
   - Queue status
   - Latency to Microservice B
4. Send data to LLM with system architecture context
5. LLM identifies bottleneck based on queue + latency patterns
6. Send diagnosis to Agent 2 (`POST /remediate`)

### Agent 2 Workflow
1. Receive diagnosis from Agent 1 (`POST /remediate`)
2. Collect deployment configs for both microservices via `oc get deployment`
3. Collect system metrics from Prometheus:
   - CPU usage (Microservice A & B)
   - Memory usage (Microservice A & B)
   - Latency metrics
4. Send all data to LLM with Kubernetes resource context
5. LLM analyzes metrics vs resource limits, generates `oc` commands
6. Execute commands: `oc set resources deployment microservice-b --limits cpu=500m`
7. Verify deployment patched successfully

## Testing Without Alerts

### Test Agent 1 directly:
```bash
oc run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent1:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"HighQueueDepth"}}]}'
```

### Test Agent 2 directly:
```bash
oc run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent2:8080/remediate \
  -H "Content-Type: application/json" \
  -d '{"diagnosis":"Test diagnosis","alert_name":"HighQueueDepth"}'
```

## Prometheus Alerts

### HighQueueDepth
- **Condition**: `queue_service_queue_depth > 10`
- **Duration**: 1 minute
- **Severity**: Warning
- **Action**: Triggers Agent 1 via Alertmanager webhook

## Architecture Details

For webhook architecture details, see [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md).

## Cleanup

```bash
chmod +x cleanup.sh
./cleanup.sh a2a-demo
```

Uninstalls Helm release and optionally deletes namespace.

## Key Differences: Agent 1 vs Agent 2

| Aspect | Agent 1 (Diagnose) | Agent 2 (Remediate) |
|--------|-------------------|---------------------|
| **Trigger** | Alertmanager webhook | Agent 1 HTTP call |
| **Access** | Microservice A metrics only | Both A & B deployment + metrics |
| **LLM Task** | Identify bottleneck location | Determine remediation action |
| **Output** | Diagnosis text | `oc` commands |
| **Action** | Call Agent 2 | Execute deployment patches |
| **Knowledge** | System architecture | Kubernetes resource management |
