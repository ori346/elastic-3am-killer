# Webhook Architecture

Event-driven agents - no polling loop

## Flow

```
Prometheus → Alertmanager → Webhook → Agent1 (FastAPI)
                                         ↓
                                    Diagnosis
                                         ↓
                                  HTTP POST /remediate
                                         ↓
                                   Agent2 (FastAPI)
                                         ↓
                                    Remediation
                                    (oc patch)
```

## Endpoints

### Agent1
- `POST /webhook` - Receives Alertmanager alerts (Alertmanager webhook format)
- `GET /health` - Kubernetes probes
- `GET /agent-card` - A2A protocol

### Agent2
- `POST /remediate` - Receives diagnosis from Agent1
- `GET /health` - Kubernetes probes
- `GET /agent-card` - A2A protocol

## Configuration

**Alertmanager is auto-configured via Helm** - no manual setup needed

```yaml
# values.yaml
prometheus:
  alertmanager:
    enabled: true  # Creates AlertmanagerConfig CRD automatically
```

The Helm chart deploys `AlertmanagerConfig` that routes `HighQueueDepth` alerts to `http://agent1:8080/webhook`.

## Testing

### Test Agent1 webhook:
```bash
oc run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent1:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighQueueDepth",
        "severity": "warning"
      }
    }]
  }'
```

### Test Agent2 remediation:
```bash
oc run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent2:8080/remediate \
  -H "Content-Type: application/json" \
  -d '{
    "diagnosis": "Microservice B is experiencing high CPU usage causing queue buildup",
    "alert_name": "HighQueueDepth"
  }'
```

### Check logs:
```bash
# Agent1 logs - should show diagnosis and Agent2 call
oc logs -f deployment/agent1

# Agent2 logs - should show remediation commands execution
oc logs -f deployment/agent2
```
