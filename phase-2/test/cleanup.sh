#!/bin/bash
set -e

NAMESPACE=${1:-integration-test}

echo "Cleaning up A2A Demo from OpenShift..."
echo "Namespace: $NAMESPACE"
echo ""

# Uninstall Helm chart
echo "Uninstalling Helm release..."
helm uninstall a2a-demo --namespace $NAMESPACE || true

# Optionally delete namespace
read -p "Delete namespace $NAMESPACE? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo "Deleting namespace..."
    oc delete namespace $NAMESPACE
    echo "Namespace deleted."
else
    echo "Namespace preserved."
fi

echo ""
echo "Cleanup complete!"
