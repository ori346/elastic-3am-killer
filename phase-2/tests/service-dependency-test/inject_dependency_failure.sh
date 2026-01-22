#!/bin/bash

# Script to inject dependency failure by scaling backend API to 0 replicas
set -e

NAMESPACE="${1:-integration-test-ofridman}"
BACKEND_DEPLOYMENT="backend-api"

echo "=========================================="
echo "Injecting Service Dependency Failure"
echo "=========================================="
echo "Namespace: $NAMESPACE"
echo "Backend Deployment: $BACKEND_DEPLOYMENT"
echo ""

# Check if deployment exists
if ! oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE" > /dev/null 2>&1; then
    echo "ERROR: Deployment $BACKEND_DEPLOYMENT not found in namespace $NAMESPACE"
    echo "Make sure you have run ./deploy.sh first"
    exit 1
fi

# Show current status
echo "Current backend deployment status:"
oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""

echo "Current backend pods:"
oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE" || echo "No backend pods found"
echo ""

# Scale backend to 0 replicas to simulate complete service failure
echo "Scaling $BACKEND_DEPLOYMENT to 0 replicas..."
oc scale deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE" --replicas=0

# Wait for pods to terminate
echo "Waiting for backend pods to terminate..."
sleep 10

# Show updated status
echo ""
echo "Updated backend deployment status:"
oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""

echo "Updated backend pods:"
oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE" || echo "No backend pods running (expected)"
echo ""

# Check frontend status (should still be running)
echo "Frontend status (should still be running):"
oc get deployment frontend-web -n "$NAMESPACE"
echo ""
oc get pods -l app=frontend-web -n "$NAMESPACE"
echo ""

# Simulate some traffic to trigger errors
echo "=========================================="
echo "Dependency Failure Injection Complete!"
echo "=========================================="
echo ""
echo "What happened:"
echo "✓ Backend API scaled to 0 replicas (simulating complete service failure)"
echo "✓ Frontend is still running but will start failing requests"
echo "✓ Frontend will experience ~95% HTTP 500 error rate"
echo "✓ Connection errors: 'Failed to connect to backend-api:8080'"
echo ""
echo "Expected behavior:"
echo "1. Frontend pods remain healthy (2/2 Ready)"
echo "2. Frontend health checks pass (but functional requests fail)"
echo "3. Frontend logs show 'Connection refused to backend-api'"
echo "4. After 1-2 minutes, FrontendHighErrorRate alert should fire"
echo ""
echo "Next steps:"
echo "1. Wait 1-2 minutes for errors to accumulate"
echo "2. Run: python send_diagnosis_to_host.py"
echo "3. Monitor agent investigation and remediation"
echo "4. Agent should discover backend has 0 replicas and scale it back up"
echo ""
echo "To verify the failure is active:"
echo "  oc logs -l app=frontend-web -n $NAMESPACE --tail=20"
echo ""
echo "To manually fix (if testing agent fails):"
echo "  oc scale deployment $BACKEND_DEPLOYMENT -n $NAMESPACE --replicas=3"
echo "=========================================="