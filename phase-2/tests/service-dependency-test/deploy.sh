#!/bin/bash

# Deploy script for service dependency test scenario
set -e

NAMESPACE="integration-test-ofridman"
HELM_RELEASE="dependency-demo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
HELM_CHART_DIR="$SCRIPT_DIR/helm/dependency-demo"

echo "================================"
echo "Service Dependency Test Deployment"
echo "================================"
echo "Namespace: $NAMESPACE"
echo "Helm Release: $HELM_RELEASE"
echo "Chart Directory: $HELM_CHART_DIR"
echo ""

# Check if namespace exists, create if it doesn't
if ! oc get namespace "$NAMESPACE" > /dev/null 2>&1; then
    echo "Creating namespace: $NAMESPACE"
    oc create namespace "$NAMESPACE"
else
    echo "Namespace $NAMESPACE already exists"
fi

# Deploy the Helm chart
echo "Deploying Helm chart..."
helm upgrade --install "$HELM_RELEASE" "$HELM_CHART_DIR" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --wait \
    --timeout=5m

echo ""
echo "Deployment successful! Waiting for all pods to be ready..."

# Wait for all deployments to be ready
echo "Waiting for frontend-web deployment to be ready..."
oc wait --for=condition=Available deployment/frontend-web -n "$NAMESPACE" --timeout=300s

echo "Waiting for backend-api deployment to be ready..."
oc wait --for=condition=Available deployment/backend-api -n "$NAMESPACE" --timeout=300s

# Wait for all pods to be ready
echo "Waiting for all pods to be ready..."
oc wait --for=condition=Ready pods --all -n "$NAMESPACE" --timeout=300s

echo ""
echo "=========================================="
echo "Service Dependency Test Environment Ready!"
echo "=========================================="
echo ""

# Display deployment status
echo "Current status:"
echo ""
echo "Deployments:"
oc get deployments -n "$NAMESPACE"
echo ""
echo "Pods:"
oc get pods -n "$NAMESPACE"
echo ""
echo "Services:"
oc get services -n "$NAMESPACE"
echo ""

# Display Prometheus monitoring resources
echo "Monitoring resources:"
if oc get servicemonitor -n "$NAMESPACE" > /dev/null 2>&1; then
    echo "ServiceMonitors:"
    oc get servicemonitor -n "$NAMESPACE"
    echo ""
fi

if oc get prometheusrule -n "$NAMESPACE" > /dev/null 2>&1; then
    echo "PrometheusRules:"
    oc get prometheusrule -n "$NAMESPACE"
    echo ""
fi

echo "==============================================="
echo "Next steps:"
echo "1. Run ./inject_dependency_failure.sh to simulate the failure"
echo "2. Run python send_diagnosis_to_host.py to send the alert"
echo "3. Monitor the agent's investigation and remediation"
echo "4. Run ./verify_dependency_fix.sh to verify the fix"
echo "5. Run ./cleanup.sh to clean up when done"
echo "==============================================="