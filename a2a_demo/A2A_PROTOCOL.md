# A2A Protocol Integration

## Overview

Both Agent1 (DiagnoseAgent) and Agent2 (RemediateAgent) now implement the **A2A (Agent-to-Agent) Protocol** using the official `a2a-sdk`. This provides:

1. **Standardized agent discovery** via AgentCard
2. **Skill-based invocation** via REST API
3. **Interoperability** with other A2A-compliant agents
4. **Backward compatibility** with custom webhooks for Alertmanager and inter-agent communication

## Architecture

```
Prometheus/Alertmanager
         ↓
   POST /webhook (custom)
         ↓
   Agent1 (A2A + Custom Endpoints)
     - AgentCard: diagnose-queue-alert skill
     - POST /webhook (Alertmanager)
     - POST /skills/diagnose-queue-alert/invoke (A2A)
     - GET /agent-card (A2A)
         ↓
   POST /remediate (custom)
         ↓
   Agent2 (A2A + Custom Endpoints)
     - AgentCard: remediate-deployment skill
     - POST /remediate (Agent1)
     - POST /skills/remediate-deployment/invoke (A2A)
     - GET /agent-card (A2A)
```

## Agent1: DiagnoseAgent

### A2A Components

#### AgentCard
```python
AgentCard(
    name="DiagnoseAgent",
    description="Diagnoses microservice performance issues...",
    version="1.0.0",
    url="http://agent1:8080",
    skills=[
        AgentSkill(
            id="diagnose-queue-alert",
            name="Diagnose Queue Depth Alert",
            description="Analyzes high queue depth alerts...",
            tags=["observability", "diagnosis", "prometheus"]
        )
    ]
)
```

#### Skills
- **diagnose-queue-alert**: Analyzes alerts by collecting metrics, diagnosing with LLM, and triggering remediation

### Endpoints

#### A2A Standard Endpoints
- `GET /agent-card` - Returns AgentCard with capabilities and skills
- `POST /skills/diagnose-queue-alert/invoke` - Invoke diagnosis skill via A2A protocol

#### Custom Endpoints
- `POST /webhook` - Receives alerts from Alertmanager (not part of A2A spec)

### Example A2A Invocation

```bash
curl -X POST http://agent1:8080/skills/diagnose-queue-alert/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "HighQueueDepth",
    "alert_labels": {"severity": "warning", "service": "microservice-a"},
    "alert_annotations": {"summary": "Queue depth exceeded"}
  }'
```

### Response
```json
{
  "agent": "DiagnoseAgent",
  "alert": "HighQueueDepth",
  "timestamp": "2025-12-08T10:30:00Z",
  "diagnostic_data": {...},
  "diagnosis": "Microservice B is CPU-constrained...",
  "status": "success",
  "agent2_response": {...}
}
```

## Agent2: RemediateAgent

### A2A Components

#### AgentCard
```python
AgentCard(
    name="RemediateAgent",
    description="Applies remediation to Kubernetes deployments...",
    version="1.0.0",
    url="http://agent2:8080",
    skills=[
        AgentSkill(
            id="remediate-deployment",
            name="Remediate Deployment",
            description="Patches deployment resource limits...",
            tags=["remediation", "kubernetes", "openshift"]
        )
    ]
)
```

#### Skills
- **remediate-deployment**: Applies remediation by patching deployments based on diagnosis

### Endpoints

#### A2A Standard Endpoints
- `GET /agent-card` - Returns AgentCard with capabilities and skills
- `POST /skills/remediate-deployment/invoke` - Invoke remediation skill via A2A protocol

#### Custom Endpoints
- `POST /remediate` - Receives remediation requests from Agent1 (not part of A2A spec)

### Example A2A Invocation

```bash
curl -X POST http://agent2:8080/skills/remediate-deployment/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "diagnosis": "Microservice B is experiencing high CPU usage causing queue buildup",
    "alert_name": "HighQueueDepth",
    "diagnostic_data": {}
  }'
```

### Response
```json
{
  "agent": "RemediateAgent",
  "alert": "HighQueueDepth",
  "timestamp": "2025-12-08T10:31:00Z",
  "current_config": {"cpu_limit": "25m", ...},
  "llm_recommendation": "Increase CPU limit to 500m...",
  "remediation_data": {...},
  "status": "success"
}
```

## A2A SDK Integration

### Technology Stack
- **Framework**: `a2a-sdk` (official A2A protocol implementation)
- **Server**: `A2ARESTFastAPIApplication` from `a2a.server.apps`
- **Handler**: `RESTHandler` from `a2a.server.request_handlers`
- **Types**: `AgentCard`, `AgentSkill`, `AgentCapabilities` from `a2a.types`

### Code Structure

Both agents follow this pattern:

```python
from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2ARESTFastAPIApplication
from a2a.server.request_handlers import RESTHandler
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

# 1. Define Agent class with business logic
class MyAgent:
    async def my_skill(self, input_data):
        # Skill implementation
        return result

# 2. Create AgentExecutor
class MyAgentExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        # Extract input from context
        # Call agent skill
        # Return result
        pass

# 3. Create AgentCard
def create_agent_card() -> AgentCard:
    return AgentCard(
        name="MyAgent",
        skills=[...],
        ...
    )

# 4. Initialize A2A application
executor = MyAgentExecutor()
agent_card = create_agent_card()
rest_handler = RESTHandler(executor=executor)
a2a_app = A2ARESTFastAPIApplication(
    agent_card=agent_card,
    http_handler=rest_handler
)

# 5. Add custom endpoints (optional)
fastapi_app = a2a_app.app
@fastapi_app.post("/custom-endpoint")
async def custom():
    ...
```

## Hybrid Approach: A2A + Custom Webhooks

### Why Hybrid?

1. **A2A Protocol**: Provides standardized discovery and invocation
2. **Custom Webhooks**: Support existing integrations (Alertmanager, inter-agent calls)

### Event Flow

```
Alert Trigger:
  Alertmanager → POST /webhook → Agent1
  (Custom, existing integration)

A2A Skill Invocation:
  External Client → POST /skills/{id}/invoke → Agent1
  (Standard A2A protocol)

Agent-to-Agent:
  Agent1 → POST /remediate → Agent2
  (Custom, optimized for this demo)

Alternative A2A Agent-to-Agent:
  Agent1 → POST /skills/remediate-deployment/invoke → Agent2
  (Standard A2A protocol, also supported!)
```

## Benefits of A2A Integration

### 1. Discoverability
```bash
# Get agent capabilities
curl http://agent1:8080/agent-card

{
  "name": "DiagnoseAgent",
  "skills": [
    {
      "id": "diagnose-queue-alert",
      "name": "Diagnose Queue Depth Alert",
      "description": "...",
      "examples": [...]
    }
  ]
}
```

### 2. Standardized Invocation
```bash
# All A2A agents use same endpoint pattern
POST /skills/{skill-id}/invoke
```

### 3. Interoperability
- Works with any A2A-compliant agent
- Agents can discover each other's capabilities
- Standard error handling and response format

### 4. Extensibility
- Easy to add new skills
- Skills can be versioned
- Support for multiple input/output modes

## Testing A2A Integration

### 1. Get AgentCard
```bash
# Agent1
curl http://agent1:8080/agent-card | jq

# Agent2
curl http://agent2:8080/agent-card | jq
```

### 2. Invoke Skills via A2A

**Agent1 - Diagnose Skill:**
```bash
kubectl run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent1:8080/skills/diagnose-queue-alert/invoke \
  -H "Content-Type: application/json" \
  -d '{"alert_name": "HighQueueDepth"}'
```

**Agent2 - Remediate Skill:**
```bash
kubectl run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://agent2:8080/skills/remediate-deployment/invoke \
  -H "Content-Type: application/json" \
  -d '{"diagnosis": "CPU-constrained", "alert_name": "HighQueueDepth"}'
```

### 3. Test Custom Webhooks (Backward Compatibility)

**Alertmanager → Agent1:**
```bash
curl -X POST http://agent1:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "HighQueueDepth"}
    }]
  }'
```

**Agent1 → Agent2:**
```bash
curl -X POST http://agent2:8080/remediate \
  -H "Content-Type: application/json" \
  -d '{
    "diagnosis": "Microservice B CPU-constrained",
    "alert_name": "HighQueueDepth"
  }'
```

## Migration from Custom FastAPI

### Before (Custom FastAPI)
```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/webhook")
async def webhook():
    ...

uvicorn.run(app, ...)
```

### After (A2A + Custom)
```python
from a2a.server.apps import A2ARESTFastAPIApplication
from a2a.server.request_handlers import RESTHandler

# Create A2A app
a2a_app = A2ARESTFastAPIApplication(
    agent_card=create_agent_card(),
    http_handler=RESTHandler(executor=executor)
)

# Get FastAPI app and add custom endpoints
fastapi_app = a2a_app.app

@fastapi_app.post("/webhook")  # Custom endpoint
async def webhook():
    ...

uvicorn.run(fastapi_app, ...)
```

## Configuration

### Environment Variables
Both agents support these standard environment variables:

- `PORT` - Server port (default: 8080)
- `LLM_ENDPOINT` - LLM service URL
- `PROMETHEUS_URL` - Prometheus endpoint
- Agent-specific variables (MICROSERVICE_A_URL, AGENT2_URL, etc.)

### Kubernetes Deployment
No changes needed! The agents expose the same ports and interfaces.

## Next Steps

### Potential A2A Enhancements

1. **Agent Discovery Service**: Central registry of A2A agents
2. **Agent Composition**: Chain multiple agents using A2A protocol
3. **Skill Orchestration**: Workflow engine for multi-agent tasks
4. **Authentication**: Add security schemes to AgentCard
5. **Streaming**: Enable streaming responses for long-running skills

### Example: Agent Composition
```python
# DiagnoseAgent discovers RemediateAgent via AgentCard
agent2_card = requests.get("http://agent2:8080/agent-card").json()

# Find remediation skill
remediate_skill = next(s for s in agent2_card['skills'] if 'remediate' in s['id'])

# Invoke via A2A protocol instead of custom webhook
response = requests.post(
    f"http://agent2:8080/skills/{remediate_skill['id']}/invoke",
    json={"diagnosis": diagnosis}
)
```

## References

- [A2A SDK Documentation](https://github.com/anthropics/a2a-sdk)
- [A2A Protocol Specification](https://modelcontextprotocol.io/introduction)
- Agent implementations: [agent1.py](agent1/agent1.py), [agent2.py](agent2/agent2.py)
