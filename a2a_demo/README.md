# A2A Multi-Agent OpenShift Demo

This directory contains the demo implementation showcasing automated incident remediation using a multi-agent system.

## Documentation

Complete documentation has been moved to [docs/demos/A2A_DEMO.md](../docs/demos/A2A_DEMO.md)

## Quick Start

```bash
# Build images
./build-images.sh --all

# Deploy to OpenShift
./deploy.sh a2a-demo

# Watch the demo
oc logs -f deployment/agent1 -n a2a-demo
oc logs -f deployment/agent2 -n a2a-demo
```

## Components

- **agent1/** - Diagnose agent (receives alerts, identifies bottlenecks)
- **agent2/** - Remediate agent (fixes issues, patches deployments)
- **microservice_a/** - Queue service (demo application)
- **microservice_b/** - Processing service (intentionally bottlenecked)
- **helm/** - Helm charts for deployment

## See Also

- [Complete Demo Documentation](../docs/demos/A2A_DEMO.md)
- [A2A Protocol](../docs/architecture/A2A_PROTOCOL.md)
- [Webhook Setup Guide](../docs/guides/WEBHOOK_SETUP.md)
