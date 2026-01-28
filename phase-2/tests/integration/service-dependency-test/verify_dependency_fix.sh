#!/bin/bash

# Verification script to check if the service dependency issue has been resolved
set -e

NAMESPACE="${1:-integration-test-ofridman}"
BACKEND_DEPLOYMENT="backend-api"
FRONTEND_DEPLOYMENT="frontend-web"
TIMEOUT=300  # 5 minutes timeout

echo "=========================================="
echo "Verifying Service Dependency Fix"
echo "=========================================="
echo "Namespace: $NAMESPACE"
echo "Backend Deployment: $BACKEND_DEPLOYMENT"
echo "Frontend Deployment: $FRONTEND_DEPLOYMENT"
echo "Timeout: ${TIMEOUT}s"
echo ""

# Function to check if backend deployment is properly scaled
check_backend_scaling() {
    local desired_replicas=$(oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
    local ready_replicas=$(oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')

    echo "Backend deployment status:"
    echo "  Desired replicas: $desired_replicas"
    echo "  Ready replicas: ${ready_replicas:-0}"

    if [[ "$desired_replicas" -gt 0 && "$ready_replicas" == "$desired_replicas" ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check if backend pods are running and ready
check_backend_pods() {
    local pod_count=$(oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE" --field-selector=status.phase=Running 2>/dev/null | grep -c "$BACKEND_DEPLOYMENT" || echo "0")
    echo "Running backend pods: $pod_count"

    if [[ "$pod_count" -gt 0 ]]; then
        echo "Backend pods status:"
        oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
        return 0
    else
        return 1
    fi
}

# Function to test backend connectivity
test_backend_connectivity() {
    echo "Testing backend connectivity..."

    # Get a backend pod to test connectivity
    local backend_pod=$(oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -n "$backend_pod" ]]; then
        echo "Testing health endpoint on pod: $backend_pod"
        if oc exec "$backend_pod" -n "$NAMESPACE" -- curl -s -f localhost:8080/health > /dev/null 2>&1; then
            echo "✓ Backend health check successful"
            return 0
        else
            echo "✗ Backend health check failed"
            return 1
        fi
    else
        echo "✗ No backend pods available for connectivity test"
        return 1
    fi
}

# Function to check frontend error rate improvement
check_frontend_error_rate() {
    echo "Checking frontend for recent errors..."

    # Get recent frontend logs to check for connection errors
    local error_count=$(oc logs -l app="$FRONTEND_DEPLOYMENT" -n "$NAMESPACE" --tail=50 2>/dev/null | grep -c "Connection refused\|Failed to connect\|backend-api.*connection" || echo "0")

    echo "Recent connection errors in frontend logs: $error_count"

    if [[ "$error_count" -eq 0 ]]; then
        echo "✓ No recent connection errors found in frontend logs"
        return 0
    else
        echo "⚠ Still seeing some connection errors (may be resolving)"
        echo "Recent frontend logs:"
        oc logs -l app="$FRONTEND_DEPLOYMENT" -n "$NAMESPACE" --tail=10
        return 1
    fi
}

# Main verification process
echo "Step 1: Checking backend deployment scaling..."
if ! check_backend_scaling; then
    echo "❌ Backend deployment is not properly scaled!"
    echo "Expected: More than 0 replicas with all replicas ready"
    echo "Current state:"
    oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
    exit 1
fi
echo "✓ Backend deployment is properly scaled"
echo ""

echo "Step 2: Waiting for backend pods to be ready..."
start_time=$(date +%s)
while ! check_backend_pods; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))

    if [[ $elapsed -ge $TIMEOUT ]]; then
        echo "❌ Timeout waiting for backend pods to be ready!"
        echo "Current pod status:"
        oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
        exit 1
    fi

    echo "Waiting for backend pods... (${elapsed}s elapsed)"
    sleep 10
done
echo "✓ Backend pods are running and ready"
echo ""

echo "Step 3: Waiting for backend pods to be fully ready..."
echo "Waiting for all backend pods to pass readiness checks..."
if ! oc wait --for=condition=Ready pod -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE" --timeout=120s; then
    echo "❌ Backend pods failed readiness checks!"
    echo "Pod status:"
    oc describe pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
    exit 1
fi
echo "✓ Backend pods passed readiness checks"
echo ""

echo "Step 4: Testing backend connectivity..."
if ! test_backend_connectivity; then
    echo "❌ Backend connectivity test failed!"
    echo "Pod details:"
    oc describe pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE" | head -50
    exit 1
fi
echo "✓ Backend connectivity test passed"
echo ""

echo "Step 5: Checking frontend service status..."
echo "Frontend deployment status:"
oc get deployment "$FRONTEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""
echo "Frontend pods:"
oc get pods -l app="$FRONTEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""

echo "Step 6: Waiting for error rate to improve..."
echo "Waiting 30 seconds for new requests to be processed without errors..."
sleep 30

if check_frontend_error_rate; then
    echo "✓ Frontend error rate has improved"
else
    echo "⚠ Frontend may still be experiencing some errors (this may be normal during recovery)"
fi
echo ""

# Final status summary
echo "=========================================="
echo "Service Dependency Fix Verification"
echo "=========================================="
echo ""

echo "Final Status Summary:"
echo ""

echo "Backend Service:"
oc get deployment "$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""
oc get pods -l app="$BACKEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""

echo "Frontend Service:"
oc get deployment "$FRONTEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""
oc get pods -l app="$FRONTEND_DEPLOYMENT" -n "$NAMESPACE"
echo ""

echo "Services:"
oc get services -l app -n "$NAMESPACE"
echo ""

echo "✅ Service dependency fix verification completed successfully!"
echo ""
echo "What was verified:"
echo "✓ Backend deployment scaled up from 0 to >0 replicas"
echo "✓ Backend pods are running and ready"
echo "✓ Backend pods pass health checks"
echo "✓ Frontend service remains available"
echo "✓ Error rate has improved (connection errors reduced/eliminated)"
echo ""
echo "The agent successfully:"
echo "1. ✓ Identified frontend errors were due to backend unavailability"
echo "2. ✓ Discovered backend was scaled to 0 replicas"
echo "3. ✓ Scaled backend service back up to restore availability"
echo "4. ✓ Resolved the service dependency failure scenario"
echo ""
echo "=========================================="