# A2A Multi-Agent OpenShift Demo

This directory contains the demo implementation showcasing automated incident remediation using a multi-agent system.


## Quick Start

```bash
# Build images
./build-images.sh --all

# Deploy to OpenShift
./deploy.sh a2a-demo

## Components

- **agent1/** - Diagnose agent (receives alerts, identifies bottlenecks)
- **agent2/** - Remediate agent (fixes issues, patches deployments)
- **microservice_a/** - Queue service (demo application)
- **microservice_b/** - Processing service (intentionally bottlenecked)
- **helm/** - Helm charts for deployment
