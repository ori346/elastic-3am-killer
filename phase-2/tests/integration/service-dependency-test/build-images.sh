#!/bin/bash

# Build and push container images for service dependency test using podman
set -e

REGISTRY="quay.io/rh-ee-ofridman"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
CONTAINERS_DIR="$SCRIPT_DIR/containers"

echo "=========================================="
echo "Building Service Dependency Test Images (Podman)"
echo "=========================================="
echo "Registry: $REGISTRY"
echo "Tag: $IMAGE_TAG"
echo "Containers directory: $CONTAINERS_DIR"
echo ""

# Function to build and push an image
build_and_push() {
    local service_name=$1
    local service_dir="$CONTAINERS_DIR/$service_name"
    local image_name="$REGISTRY/$service_name:$IMAGE_TAG"

    echo "Building $service_name..."
    echo "  Source directory: $service_dir"
    echo "  Image name: $image_name"

    if [[ ! -d "$service_dir" ]]; then
        echo "ERROR: Directory $service_dir does not exist"
        exit 1
    fi

    if [[ ! -f "$service_dir/Containerfile" ]]; then
        echo "ERROR: Containerfile not found in $service_dir"
        exit 1
    fi

    # Build the image
    echo "  Building image..."
    if ! podman build -t "$image_name" -f "$service_dir/Containerfile" "$service_dir"; then
        echo "ERROR: Failed to build $service_name image"
        exit 1
    fi

    echo "  ✓ Built $image_name"

    # Push the image
    echo "  Pushing image to registry..."
    if ! podman push "$image_name"; then
        echo "ERROR: Failed to push $service_name image"
        exit 1
    fi

    echo "  ✓ Pushed $image_name"
    echo ""
}

# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo "ERROR: Podman is not installed or not in PATH"
    echo "To install podman:"
    echo "  # On RHEL/CentOS/Fedora:"
    echo "  sudo dnf install podman"
    echo "  # On Ubuntu/Debian:"
    echo "  sudo apt install podman"
    exit 1
fi

# Check if podman is working
if ! podman info &> /dev/null; then
    echo "ERROR: Podman is not working properly"
    echo "Try running: podman system reset"
    exit 1
fi

# Check registry authentication (skip detailed check, assume user is logged in)
echo "Checking registry authentication..."
if ! podman login --get-login "$REGISTRY" &> /dev/null; then
    echo "You may need to login to the registry first:"
    echo "  podman login $REGISTRY"
    echo ""
    read -p "Do you want to continue with the build? (y/N): " continue_build
    case $continue_build in
        [Yy]* )
            echo "Continuing with build..."
            ;;
        * )
            echo "Build cancelled"
            exit 1
            ;;
    esac
else
    echo "✓ Registry authentication confirmed"
fi

# Build and push all images
echo "Starting image builds..."
echo ""

build_and_push "frontend-web"
build_and_push "backend-api"
build_and_push "dependency-client"

echo "=========================================="
echo "All images built and pushed successfully!"
echo "=========================================="
echo ""

echo "Built images:"
echo "  $REGISTRY/frontend-web:$IMAGE_TAG"
echo "  $REGISTRY/backend-api:$IMAGE_TAG"
echo "  $REGISTRY/dependency-client:$IMAGE_TAG"
echo ""

echo "To verify the images:"
echo "  podman images | grep $REGISTRY"
echo ""

echo "To test an image locally:"
echo "  podman run -p 8080:8080 $REGISTRY/frontend-web:$IMAGE_TAG"
echo "  podman run -p 8080:8080 $REGISTRY/backend-api:$IMAGE_TAG"
echo "  podman run -p 8081:8081 $REGISTRY/dependency-client:$IMAGE_TAG"
echo ""

echo "Next steps:"
echo "1. The images are now available for the OpenShift deployment"
echo "2. Run ./deploy.sh to deploy the test environment"
echo "3. Run ./inject_dependency_failure.sh to trigger the failure scenario"
echo ""