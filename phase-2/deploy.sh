#!/bin/bash
set -e

NAMESPACE="${1:-integration-test}"
RELEASE_NAME="${2:-elastic-3am-killer}"
VALUES_FILE="${3:-values-file.yaml}"

echo "Deploying to namespace: $NAMESPACE"
echo "Release name: $RELEASE_NAME"


# Deploy with Helm
helm upgrade --install $RELEASE_NAME ./helm \
  --namespace $NAMESPACE \
  -f $VALUES_FILE \
  --wait

echo ""
echo "Deployment complete!"
echo ""
echo "Check status:"
echo "  oc get pods -n $NAMESPACE"
echo "  oc logs -f deployment/$RELEASE_NAME -n $NAMESPACE"
echo ""
echo "Get route:"
echo "  oc get route $RELEASE_NAME -n $NAMESPACE"
