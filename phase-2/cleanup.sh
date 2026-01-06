#!/bin/bash
set -e

NAMESPACE="${1:-integration-test}"
RELEASE_NAME="${2:-elastic-3am-killer}"

echo "Cleaning up deployment from namespace: $NAMESPACE"
echo "Release name: $RELEASE_NAME"

# Uninstall Helm release
helm uninstall $RELEASE_NAME -n $NAMESPACE || true

# Delete namespace (optional, commented out by default)
# oc delete namespace $NAMESPACE

echo ""
echo "Cleanup complete!"
