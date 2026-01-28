#!/bin/bash

# Cleanup script for service dependency test scenario
set -e

NAMESPACE=${1:-integration-test-ofridman}
HELM_RELEASE=${2:-dependency-demo}

echo "========================================"
echo "Service Dependency Test Cleanup"
echo "========================================"
echo "Namespace: $NAMESPACE"
echo "Helm Release: $HELM_RELEASE"
echo ""

# Check if Helm release exists
if helm list -n "$NAMESPACE" | grep -q "$HELM_RELEASE"; then
    echo "Uninstalling Helm release: $HELM_RELEASE"
    helm uninstall "$HELM_RELEASE" -n "$NAMESPACE"
    echo "Helm release uninstalled successfully"
else
    echo "Helm release $HELM_RELEASE not found, skipping Helm uninstall"
fi

# Wait a bit for resources to be cleaned up
echo "Waiting for resources to be cleaned up..."
sleep 5

# Check for remaining resources and clean them up
echo "Checking for remaining resources..."

# Clean up any remaining deployments
if oc get deployments -n "$NAMESPACE" 2>/dev/null | grep -E "(frontend-web|backend-api)" > /dev/null; then
    echo "Cleaning up remaining deployments..."
    oc delete deployment frontend-web backend-api -n "$NAMESPACE" --ignore-not-found=true
fi

# Clean up any remaining services
if oc get services -n "$NAMESPACE" 2>/dev/null | grep -E "(frontend-web|backend-api)" > /dev/null; then
    echo "Cleaning up remaining services..."
    oc delete service frontend-web backend-api -n "$NAMESPACE" --ignore-not-found=true
fi

# Clean up ServiceMonitors
if oc get servicemonitor -n "$NAMESPACE" 2>/dev/null | grep -E "(frontend-web|backend-api)" > /dev/null; then
    echo "Cleaning up ServiceMonitors..."
    oc delete servicemonitor frontend-web backend-api -n "$NAMESPACE" --ignore-not-found=true
fi

# Clean up PrometheusRules
if oc get prometheusrule -n "$NAMESPACE" 2>/dev/null | grep "frontend-high-error-rate" > /dev/null; then
    echo "Cleaning up PrometheusRules..."
    oc delete prometheusrule frontend-high-error-rate -n "$NAMESPACE" --ignore-not-found=true
fi

# Final verification
echo ""
echo "Final verification:"
echo "Deployments remaining:"
oc get deployments -n "$NAMESPACE" 2>/dev/null | grep -E "(frontend-web|backend-api)" || echo "None"
echo ""
echo "Services remaining:"
oc get services -n "$NAMESPACE" 2>/dev/null | grep -E "(frontend-web|backend-api)" || echo "None"
echo ""
echo "Pods remaining:"
oc get pods -n "$NAMESPACE" 2>/dev/null | grep -E "(frontend-web|backend-api)" || echo "None"
echo ""

echo "============================================"
echo "Service Dependency Test Cleanup Complete!"
echo "============================================"

# Ask if user wants to delete the namespace
echo ""
read -p "Do you want to delete the entire namespace '$NAMESPACE'? (y/N): " delete_namespace
case $delete_namespace in
    [Yy]* )
        echo "Deleting namespace: $NAMESPACE"
        oc delete namespace "$NAMESPACE" --ignore-not-found=true
        echo "Namespace deleted successfully"
        ;;
    * )
        echo "Keeping namespace: $NAMESPACE"
        echo "Note: Other resources may still exist in this namespace"
        ;;
esac

echo "Cleanup complete!"