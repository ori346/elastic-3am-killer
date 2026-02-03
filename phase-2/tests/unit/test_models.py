"""
import pytest

Tests for ToolResult system Pydantic models.

This module tests all the data models used by the ToolResult system,
including validation, serialization, and computed properties.
"""

import pytest
from agents.remediation.models import (
    ContainerDetail,
    DeploymentCondition,
    DeploymentDetail,
    ErrorType,
    EventType,
    LogEntry,
    OpenShiftEvent,
    PodDetail,
    PodDetailedResult,
    ToolError,
    ToolResult,
)
from pydantic import ValidationError


class TestDeploymentCondition:
    """Test DeploymentCondition model"""

    def test_deployment_condition_valid(self):
        """Test valid deployment condition creation"""
        condition = DeploymentCondition(
            type="Available",
            status="True",
            reason="MinimumReplicasAvailable",
            message="Deployment has minimum availability.",
        )
        assert condition.type == "Available"
        assert condition.status == "True"
        assert condition.reason == "MinimumReplicasAvailable"
        assert condition.message == "Deployment has minimum availability."

    def test_deployment_condition_optional_fields(self):
        """Test deployment condition with optional fields"""
        condition = DeploymentCondition(type="Progressing", status="False")
        assert condition.type == "Progressing"
        assert condition.reason is None
        assert condition.message is None


class TestOpenShiftEvent:
    """Test OpenShiftEvent model"""

    def test_event_warning(self):
        """Test warning event creation"""
        event = OpenShiftEvent(
            type=EventType.WARNING,
            reason="FailedScheduling",
            message="0/3 nodes are available: 3 Insufficient cpu.",
            object="pod/backend-db",
            count=5,
        )
        assert event.type == EventType.WARNING
        assert event.reason == "FailedScheduling"
        assert event.count == 5

    def test_event_normal(self):
        """Test normal event creation"""
        event = OpenShiftEvent(
            type=EventType.NORMAL,
            reason="Pulled",
            message="Successfully pulled image",
            object="pod/frontend",
        )
        assert event.type == EventType.NORMAL
        assert event.count == 1  # Default

    def test_event_type_enum(self):
        """Test EventType enum values"""
        assert EventType.NORMAL == "Normal"
        assert EventType.WARNING == "Warning"


class TestLogEntry:
    """Test LogEntry model"""

    def test_log_entry_complete(self):
        """Test log entry with all fields"""
        entry = LogEntry(
            level="ERROR", message="Database connection failed", container="backend"
        )
        assert entry.level == "ERROR"
        assert entry.message == "Database connection failed"
        assert entry.container == "backend"

    def test_log_entry_minimal(self):
        """Test log entry with only required fields"""
        entry = LogEntry(message="Application started")
        assert entry.message == "Application started"
        assert entry.level is None
        assert entry.container is None


class TestToolError:
    """Test ToolError model"""

    def test_tool_error_complete(self):
        """Test tool error with all fields"""
        error = ToolError(
            tool_name="test_tool",
            type=ErrorType.PERMISSION,
            message="Access denied to namespace",
            recoverable=False,
            suggestion="Check RBAC permissions",
            raw_output="error: You must be logged in",
        )
        assert error.type == ErrorType.PERMISSION
        assert error.message == "Access denied to namespace"
        assert error.recoverable is False
        assert error.suggestion == "Check RBAC permissions"
        assert error.raw_output == "error: You must be logged in"

    def test_tool_error_minimal(self):
        """Test tool error with only required fields"""
        error = ToolError(
            tool_name="test_tool",
            type=ErrorType.UNKNOWN,
            message="Unexpected error",
            recoverable=True,
            suggestion="Try again later",
        )
        assert error.type == ErrorType.UNKNOWN
        assert error.recoverable is True
        assert error.raw_output is None

    def test_error_type_enum(self):
        """Test ErrorType enum values"""
        assert ErrorType.NOT_FOUND == "not_found"
        assert ErrorType.PERMISSION == "permission"
        assert ErrorType.TIMEOUT == "timeout"
        assert ErrorType.SYNTAX == "syntax"
        assert ErrorType.NETWORK == "network"
        assert ErrorType.RESOURCE_LIMIT == "resource_limit"
        assert ErrorType.CONFIGURATION == "configuration"
        assert ErrorType.UNKNOWN == "unknown"


# Legacy ToolResult tests removed - we now use specific result types instead


class TestContainerDetail:
    """Test ContainerDetail model"""

    def test_container_detail_valid(self):
        """Test valid container detail creation with all fields"""
        container = ContainerDetail(
            name="nginx-debug",
            image="nginx:1.21-alpine",
            ready=True,
            restart_count=2,
            state="running",
            limits={"cpu": "1000m", "memory": "512Mi"},
            requests={"cpu": "200m", "memory": "128Mi"},
            liveness_probe={
                "httpGet": {"path": "/health", "port": 8080},
                "initialDelaySeconds": 30,
            },
            readiness_probe={
                "httpGet": {"path": "/ready", "port": 8080},
                "periodSeconds": 10,
            },
            exit_code=None,
            termination_reason=None,
            termination_message=None,
            ports=[{"containerPort": 80, "protocol": "TCP"}],
            environment=[{"name": "ENV", "value": "production"}],
        )
        assert container.name == "nginx-debug"
        assert container.image == "nginx:1.21-alpine"
        assert container.ready is True
        assert container.restart_count == 2
        assert container.state == "running"
        assert container.limits["cpu"] == "1000m"
        assert container.requests["memory"] == "128Mi"
        assert container.liveness_probe["httpGet"]["path"] == "/health"
        assert container.readiness_probe["periodSeconds"] == 10
        assert len(container.ports) == 1
        assert container.ports[0]["containerPort"] == 80
        assert len(container.environment) == 1
        assert container.environment[0]["name"] == "ENV"

    def test_container_detail_required_only(self):
        """Test container detail with only required fields"""
        container = ContainerDetail(
            name="minimal-container",
            image="alpine:latest",
            ready=False,
            restart_count=0,
            state="waiting",
        )
        assert container.name == "minimal-container"
        assert container.ready is False
        assert container.restart_count == 0
        assert container.state == "waiting"
        assert container.limits is None
        assert container.requests is None
        assert container.liveness_probe is None
        assert container.readiness_probe is None
        assert container.exit_code is None
        assert container.termination_reason is None
        assert container.termination_message is None
        assert len(container.ports) == 0  # Default empty list
        assert len(container.environment) == 0  # Default empty list

    def test_container_detail_terminated_state(self):
        """Test container detail with termination information"""
        container = ContainerDetail(
            name="crashed-container",
            image="buggy-app:v1.0",
            ready=False,
            restart_count=5,
            state="terminated",
            exit_code=1,
            termination_reason="Error",
            termination_message="Container failed to start",
        )
        assert container.state == "terminated"
        assert container.exit_code == 1
        assert container.termination_reason == "Error"
        assert container.termination_message == "Container failed to start"

    def test_container_detail_validation_error(self):
        """Test container detail validation errors"""
        with pytest.raises(ValidationError):
            ContainerDetail()  # Missing required fields


class TestPodDetail:
    """Test PodDetail model"""

    def test_pod_detail_valid(self):
        """Test valid pod detail creation with all fields"""
        pod = PodDetail(
            name="web-app-pod-abc123",
            status="Running",
            ready="2/2",
            restarts=1,
            pod_ip="10.128.2.15",
            host_ip="192.168.1.100",
            labels={"app": "web-app", "version": "v1.2"},
            annotations={"deployment.kubernetes.io/revision": "3"},
            service_account="web-app-sa",
            security_context={
                "runAsUser": 1001,
                "runAsGroup": 1001,
                "fsGroup": 1001,
            },
            owner_references=[{"kind": "ReplicaSet", "name": "web-app-rs-xyz789"}],
        )
        assert pod.name == "web-app-pod-abc123"
        assert pod.status == "Running"
        assert pod.ready == "2/2"
        assert pod.restarts == 1
        assert pod.pod_ip == "10.128.2.15"
        assert pod.host_ip == "192.168.1.100"
        assert pod.labels["app"] == "web-app"
        assert pod.annotations["deployment.kubernetes.io/revision"] == "3"
        assert pod.service_account == "web-app-sa"
        assert pod.security_context["runAsUser"] == 1001
        assert len(pod.owner_references) == 1
        assert pod.owner_references[0]["kind"] == "ReplicaSet"

    def test_pod_detail_minimal(self):
        """Test pod detail with only required fields"""
        pod = PodDetail(
            name="minimal-pod",
            status="Pending",
            ready="0/1",
            restarts=0,
        )
        assert pod.name == "minimal-pod"
        assert pod.status == "Pending"
        assert pod.ready == "0/1"
        assert pod.restarts == 0
        assert pod.pod_ip is None
        assert pod.host_ip is None
        assert len(pod.labels) == 0  # Default empty dict
        assert len(pod.annotations) == 0  # Default empty dict
        assert pod.service_account is None
        assert pod.security_context is None
        assert len(pod.owner_references) == 0  # Default empty list

    def test_pod_detail_validation_error(self):
        """Test pod detail validation errors"""
        with pytest.raises(ValidationError):
            PodDetail()  # Missing required fields


class TestPodDetailedResult:
    """Test PodDetailedResult model"""

    def test_pod_detailed_result_valid(self):
        """Test valid pod detailed result creation"""
        pod_detail = PodDetail(
            name="test-pod",
            status="Running",
            ready="1/1",
            restarts=0,
            pod_ip="10.1.1.1",
        )
        container_detail = ContainerDetail(
            name="main-container",
            image="nginx:latest",
            ready=True,
            restart_count=0,
            state="running",
        )

        result = PodDetailedResult(
            tool_name="execute_oc_describe_pod",
            namespace="test-namespace",
            pod=pod_detail,
            containers=[container_detail],
        )

        assert result.tool_name == "execute_oc_describe_pod"
        assert result.namespace == "test-namespace"
        assert result.pod.name == "test-pod"
        assert len(result.containers) == 1
        assert result.containers[0].name == "main-container"

    def test_pod_detailed_result_multiple_containers(self):
        """Test pod detailed result with multiple containers"""
        pod_detail = PodDetail(
            name="multi-container-pod",
            status="Running",
            ready="3/3",
            restarts=0,
        )
        containers = []
        for i in range(3):
            container = ContainerDetail(
                name=f"container-{i}",
                image=f"image-{i}:latest",
                ready=True,
                restart_count=0,
                state="running",
            )
            containers.append(container)

        result = PodDetailedResult(
            tool_name="execute_oc_describe_pod",
            namespace="production",
            pod=pod_detail,
            containers=containers,
        )

        assert len(result.containers) == 3
        assert result.containers[1].name == "container-1"

    def test_pod_detailed_result_validation_error(self):
        """Test pod detailed result validation errors"""
        with pytest.raises(ValidationError):
            PodDetailedResult()  # Missing required fields


class TestDeploymentDetail:
    """Test DeploymentDetail model"""

    def test_deployment_detail_valid(self):
        """Test valid deployment detail creation with all fields"""
        conditions = [
            DeploymentCondition(
                type="Available",
                status="True",
                reason="MinimumReplicasAvailable",
                message="Deployment has minimum availability.",
            ),
            DeploymentCondition(
                type="Progressing",
                status="True",
                reason="NewReplicaSetAvailable",
                message="ReplicaSet has successfully progressed.",
            ),
        ]

        deployment = DeploymentDetail(
            tool_name="execute_oc_describe_deployment",
            namespace="production",
            name="web-app-deployment",
            ready_replicas=5,
            desired_replicas=5,
            available_replicas=5,
            updated_replicas=5,
            unavailable_replicas=0,
            strategy_type="RollingUpdate",
            max_surge="25%",
            max_unavailable="25%",
            observed_generation=10,
            progress_deadline_seconds=600,
            labels={"app": "web-app", "env": "production"},
            selector_labels={"app": "web-app", "version": "stable"},
            conditions=conditions,
        )

        assert deployment.tool_name == "execute_oc_describe_deployment"
        assert deployment.namespace == "production"
        assert deployment.name == "web-app-deployment"
        assert deployment.ready_replicas == 5
        assert deployment.desired_replicas == 5
        assert deployment.available_replicas == 5
        assert deployment.updated_replicas == 5
        assert deployment.unavailable_replicas == 0
        assert deployment.strategy_type == "RollingUpdate"
        assert deployment.max_surge == "25%"
        assert deployment.max_unavailable == "25%"
        assert deployment.observed_generation == 10
        assert deployment.progress_deadline_seconds == 600
        assert deployment.labels["app"] == "web-app"
        assert deployment.selector_labels["version"] == "stable"
        assert len(deployment.conditions) == 2
        assert deployment.conditions[0].type == "Available"

    def test_deployment_detail_minimal(self):
        """Test deployment detail with only required fields"""
        deployment = DeploymentDetail(
            namespace="test",
            name="minimal-deployment",
            desired_replicas=1,
        )

        assert deployment.name == "minimal-deployment"
        assert deployment.namespace == "test"
        assert deployment.desired_replicas == 1
        assert deployment.ready_replicas == 0  # Default
        assert deployment.available_replicas == 0  # Default
        assert deployment.updated_replicas == 0  # Default
        assert deployment.unavailable_replicas == 0  # Default
        assert deployment.strategy_type is None
        assert deployment.max_surge is None
        assert deployment.max_unavailable is None
        assert deployment.observed_generation is None
        assert deployment.progress_deadline_seconds is None
        assert len(deployment.labels) == 0  # Default empty dict
        assert len(deployment.selector_labels) == 0  # Default empty dict
        assert len(deployment.conditions) == 0  # Default empty list

    def test_deployment_detail_default_tool_name(self):
        """Test deployment detail uses default tool name"""
        deployment = DeploymentDetail(
            namespace="test",
            name="test-deployment",
            desired_replicas=1,
        )
        # Should use the default value from the model
        assert deployment.tool_name == "execute_oc_describe_deployment"

    def test_deployment_detail_validation_error(self):
        """Test deployment detail validation errors"""
        with pytest.raises(ValidationError):
            DeploymentDetail()  # Missing required fields

    def test_deployment_detail_scaling_scenario(self):
        """Test deployment detail for scaling troubleshooting scenario"""
        deployment = DeploymentDetail(
            namespace="staging",
            name="scaling-app",
            desired_replicas=10,
            ready_replicas=7,
            available_replicas=7,
            updated_replicas=8,
            unavailable_replicas=3,
            strategy_type="RollingUpdate",
            max_surge="2",
            max_unavailable="1",
            observed_generation=5,
            conditions=[
                DeploymentCondition(
                    type="Progressing",
                    status="True",
                    reason="ReplicaSetUpdated",
                    message="Updated replica set has 8 replicas",
                )
            ],
        )

        # Verify scaling-related fields for debugging
        assert deployment.desired_replicas == 10
        assert deployment.ready_replicas == 7
        assert deployment.unavailable_replicas == 3
        assert deployment.max_surge == "2"
        assert deployment.max_unavailable == "1"
        assert deployment.conditions[0].reason == "ReplicaSetUpdated"
