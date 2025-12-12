#!/bin/bash
set -e

# Parse command line arguments
BUILD_ALL=true
BUILD_MICROSERVICES=false
BUILD_CLIENT=false
BUILD_AGENTS=false

if [ $# -gt 0 ]; then
    BUILD_ALL=false
    for arg in "$@"; do
        case $arg in
            --microservices)
                BUILD_MICROSERVICES=true
                ;;
            --client)
                BUILD_CLIENT=true
                ;;
            --agents)
                BUILD_AGENTS=true
                ;;
            --all)
                BUILD_ALL=true
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --microservices  Build only microservices (microservice-a and microservice-b)"
                echo "  --client         Build only client simulator"
                echo "  --agents         Build only agents (agent1 and agent2)"
                echo "  --all            Build all images (default)"
                echo "  --help           Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0                    # Build all images"
                echo "  $0 --agents           # Build only agents"
                echo "  $0 --agents --client  # Build agents and client"
                exit 0
                ;;
            *)
                echo "Unknown option: $arg"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
fi

echo "Building container images for A2A Demo using Podman..."
echo ""

# Build Microservices
if [ "$BUILD_ALL" = true ] || [ "$BUILD_MICROSERVICES" = true ]; then
    echo "Building Microservice B..."
    podman build -t quay.io/rh-ee-ofridman/microservice-b:latest ./microservice_b/ && \
    podman push quay.io/rh-ee-ofridman/microservice-b:latest

    echo "Building Microservice A..."
    podman build -t quay.io/rh-ee-ofridman/microservice-a:latest ./microservice_a/ && \
    podman push quay.io/rh-ee-ofridman/microservice-a:latest
fi

# Build Client Simulator
if [ "$BUILD_ALL" = true ] || [ "$BUILD_CLIENT" = true ]; then
    echo "Building Client Simulator..."
    podman build -t quay.io/rh-ee-ofridman/client-simulator:latest ./client/ && \
    podman push quay.io/rh-ee-ofridman/client-simulator:latest
fi

# Build Agents
if [ "$BUILD_ALL" = true ] || [ "$BUILD_AGENTS" = true ]; then
    echo "Building Agent 1..."
    podman build -t quay.io/rh-ee-ofridman/agent1:latest ./agent1/ && \
    podman push quay.io/rh-ee-ofridman/agent1:latest

    echo "Building Agent 2..."
    podman build -t quay.io/rh-ee-ofridman/agent2:latest ./agent2/ && \
    podman push quay.io/rh-ee-ofridman/agent2:latest
fi

echo ""
echo "Build completed successfully!"
echo ""

# Show what was built
if [ "$BUILD_ALL" = true ]; then
    echo "Built images:"
    echo "  - quay.io/rh-ee-ofridman/microservice-b:latest"
    echo "  - quay.io/rh-ee-ofridman/microservice-a:latest"
    echo "  - quay.io/rh-ee-ofridman/client-simulator:latest"
    echo "  - quay.io/rh-ee-ofridman/agent1:latest"
    echo "  - quay.io/rh-ee-ofridman/agent2:latest"
elif [ "$BUILD_AGENTS" = true ]; then
    echo "Built agent images:"
    echo "  - quay.io/rh-ee-ofridman/agent1:latest"
    echo "  - quay.io/rh-ee-ofridman/agent2:latest"
fi
echo ""
