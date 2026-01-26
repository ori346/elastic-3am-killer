# 3AM Alert Killer

An intelligent multi-agent system for automated incident remediation in OpenShift environments. The system uses LLM-powered agents to diagnose issues, execute remediation commands, and generate comprehensive reports - so you don't have to wake up at 3 AM.

## Overview

The 3AM Alert Killer implements multi-agent architecture where specialized agents collaborate to handle incidents automatically:


- **Remediation Agent**: Does exhaustive research about the alert. Collects resources metadata, metrics, and logs to find the cause and create commands that remediate the alert.
- **Report Agent**: Generates incident reports using the protocol transcript so the engineer can see what has been done quickly and easily.
- **Host Agent**: Orchestrates the remediation workflow. Designed with A2A protocol so you can use any kind of agent to resolve the issue.

The agents work together to receive alerts, diagnose problems, execute fixes, verify resolution, and deliver comprehensive reports to your team.


### Agents Flow
1. Host Agent receives an alert and asks the remediation agent to analyze and come up with remediation commands.
2. Remediation agent reads the microservice info. Then, the agent can use tools to collect data about the cluster state. Eventually, when it identifies the problem, it generates remediation commands with a short explanation and hands them off to the host agent.
3. The host agent runs the commands and stores the command execution results. If the commands execute successfully, the agent verifies that the alert resolves and asks the report agent to generate a report.
4. The report agent collects all the relevant data from the transcript and generates a short and concise report with relevant data for the engineer.
5. The report is stored in the context, and the protocol is marked as complete. 

## Quick Start

### Phase 2: Production System
Deploy the full multi-agent system:
Create `values-file.yaml` with the following:

```yaml
# Shared LLM Configuration (used by all agents)
llm:
  apiBase: "https://your-model-endpoint/v1"
  apiKey: "your api key"
  model: "model name"

# Optional: Override for specific agents (leave empty to use shared config)
hostAgent:
  llm:
    apiBase: ""
    apiKey: ""
    model: ""

remediationAgent:
  llm:
    apiBase: ""
    apiKey: ""
    model: ""

reportMakerAgent:
  llm:
    apiBase: ""
    apiKey: ""
    model: ""

# Microservices info describing your system architecture
microservicesInfo:
  content: |
    Write a SHORT explanation about the microservices and the system.
```

When you set all the above, we're ready to deploy the agents system
```bash
cd phase-2
NAMESPACE=<namespace> ./deploy.sh
```


## Requirements

### Software
- **OpenShift** with admin permissions (for production deployment)
- **LLM endpoint** with OpenAI-compatible API

### Optional
- **Prometheus & Alertmanager** (for monitoring integration)

### Permissions
- **Namespace admin** permissions for deployment
- **RBAC** for pod/deployment operations (scale, patch, rollout)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Host Agent (A2A)                      │
│  - Receives alerts via A2A protocol                         |
|  - Orchestrates remediation workflow                        │
│  - Stores remediation reports in context                    │
│                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐         │
│  │ Remediation Agent    │  │ Report Agent         │         │
│  │ - Generate commands  │  │ - Generate reports   │         │
│  │ - Validate allowlist │  │ - Store in context   │         │
│  └──────────────────────┘  └──────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
                             ▲
                             │   A2A
                             │ Protocol
                             │
                             ▼
                    ┌────────────────┐
                    │  Elastic Agent │
                    └────────────────┘
```


## Contributing

We welcome contributions! To test your changes locally:

### Local Testing Setup

1. **Deploy the test environment** (includes test microservices and client agent)
```bash
cd phase-2/test
NAMESPACE=<tests-name-space> ./deploy.sh
```

2. **Set environment variables** for the agents
```bash
export API_BASE=https://<your-model-endpoint>/v1
export API_KEY=<api-key> # or $(oc whoami -t)
export MODEL=<model-name>
```

3. **Start the agents locally** (no need to build or push images)
```bash
cd ../app
uv init # First time only
uv sync
uv uvicorn main:app --port 5001
```

4. **Trigger a test alert** to simulate the client agent diagnosis
```bash
cd ../test
python send_diagnosis_to_host.py
```

After testing your changes, submit a pull request with a clear description of your improvements.
