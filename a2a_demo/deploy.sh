#!/bin/bash
set -e

NAMESPACE=${1:-a2a-demo}
AGENT_URL=${2:-""}

echo "Deploying A2A Demo to OpenShift..."
echo "Namespace: $NAMESPACE"
echo "Agent URL: $AGENT_URL"
echo ""

# Create namespace if it doesn't exist
echo "Creating namespace..."
oc create namespace $NAMESPACE --dry-run=client -o yaml | oc apply -f -

# Deploy using Helm
echo "Deploying with Helm..."
helm upgrade --install a2a-demo ./helm/a2a-demo \
  --namespace $NAMESPACE \
  --set global.agentUrl="$AGENT_URL" \
  --wait

echo ""
echo "Deployment complete!"
echo ""
echo "Check status:"
echo "  oc get pods -n $NAMESPACE"
echo ""
echo "View logs:"
echo "  oc logs -f deployment/microservice-a -n $NAMESPACE"
echo "  oc logs -f deployment/microservice-b -n $NAMESPACE"
echo "  oc logs -f deployment/client-simulator -n $NAMESPACE"
echo ""
echo "Check metrics:"
echo "  oc port-forward svc/microservice-a 8080:8080 -n $NAMESPACE"
echo "  curl http://localhost:8080/metrics"
