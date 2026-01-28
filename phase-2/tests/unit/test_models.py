"""
import pytest

Tests for ToolResult system Pydantic models.

This module tests all the data models used by the ToolResult system,
including validation, serialization, and computed properties.
"""

import pytest
from agents.remediation.models import (
    ContainerInfo,
    DeploymentCondition,
    DeploymentInfo,
    ErrorType,
    EventType,
    LogEntry,
    LogResponse,
    OpenShiftEvent,
    PodCondition,
    PodInfo,
    ResourceRequirements,
    ToolError,
    ToolResult,
)
from pydantic import ValidationError


class TestResourceRequirements:
    """Test ResourceRequirements model"""

    def test_resource_requirements_valid(self):
        """Test valid resource requirements creation"""
        resources = ResourceRequirements(cpu="500m", memory="256Mi")
        assert resources.cpu == "500m"
        assert resources.memory == "256Mi"

    def test_resource_requirements_optional_fields(self):
        """Test resource requirements with optional fields"""
        # CPU only
        resources = ResourceRequirements(cpu="1000m")
        assert resources.cpu == "1000m"
        assert resources.memory is None

        # Memory only
        resources = ResourceRequirements(memory="512Mi")
        assert resources.cpu is None
        assert resources.memory == "512Mi"

        # Empty
        resources = ResourceRequirements()
        assert resources.cpu is None
        assert resources.memory is None


class TestContainerInfo:
    """Test ContainerInfo model"""

    def test_container_info_valid(self, sample_resource_requirements):
        """Test valid container info creation"""
        container = ContainerInfo(
            name="nginx",
            image="nginx:1.20",
            ready=True,
            restart_count=0,
            state="running",
            limits=sample_resource_requirements,
            requests=sample_resource_requirements,
        )
        assert container.name == "nginx"
        assert container.image == "nginx:1.20"
        assert container.ready is True
        assert container.restart_count == 0
        assert container.state == "running"
        assert container.limits.cpu == "500m"
        assert container.requests.memory == "256Mi"

    def test_container_info_required_fields(self):
        """Test container info with only required fields"""
        container = ContainerInfo(
            name="minimal", image="alpine:latest", ready=False, state="waiting"
        )
        assert container.name == "minimal"
        assert container.restart_count == 0  # Default value
        assert container.limits is None
        assert container.requests is None

    def test_container_info_validation_error(self):
        """Test container info validation errors"""
        with pytest.raises(ValidationError):
            ContainerInfo()  # Missing required fields


class TestPodCondition:
    """Test PodCondition model"""

    def test_pod_condition_valid(self):
        """Test valid pod condition creation"""
        condition = PodCondition(type="Ready", status="True", reason="PodReady")
        assert condition.type == "Ready"
        assert condition.status == "True"
        assert condition.reason == "PodReady"

    def test_pod_condition_optional_reason(self):
        """Test pod condition without reason"""
        condition = PodCondition(type="PodScheduled", status="True")
        assert condition.type == "PodScheduled"
        assert condition.reason is None


class TestPodInfo:
    """Test PodInfo model"""

    def test_pod_info_valid(self, sample_container_info, sample_pod_condition):
        """Test valid pod info creation"""
        pod = PodInfo(
            name="test-pod",
            namespace="test-ns",
            status="Running",
            ready="1/1",
            age="5m",  # Add required age field
            containers=[sample_container_info],
            conditions=[sample_pod_condition],
        )
        assert pod.name == "test-pod"
        assert pod.namespace == "test-ns"
        assert pod.status == "Running"
        assert pod.ready == "1/1"
        assert len(pod.containers) == 1
        assert len(pod.conditions) == 1
        assert pod.restarts == 0  # Default
        assert pod.service_account == "default"  # Default

    def test_pod_info_empty_containers_and_conditions(self):
        """Test pod info with empty containers and conditions"""
        pod = PodInfo(
            name="empty-pod",
            namespace="test-ns",
            status="Pending",
            ready="0/0",
            age="1m",  # Add required age field
        )
        assert len(pod.containers) == 0
        assert len(pod.conditions) == 0

    def test_pod_info_validation_error(self):
        """Test pod info validation errors"""
        with pytest.raises(ValidationError):
            PodInfo()  # Missing required fields


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


class TestDeploymentInfo:
    """Test DeploymentInfo model"""

    def test_deployment_info_valid(self, sample_deployment_condition):
        """Test valid deployment info creation"""
        deployment = DeploymentInfo(
            name="web-app",
            namespace="production",
            desired_replicas=5,
            ready_replicas=3,
            available_replicas=3,
            updated_replicas=4,
            strategy="RollingUpdate",
            conditions=[sample_deployment_condition],
        )
        assert deployment.name == "web-app"
        assert deployment.namespace == "production"
        assert deployment.desired_replicas == 5
        assert deployment.ready_replicas == 3
        assert deployment.available_replicas == 3
        assert deployment.updated_replicas == 4
        assert deployment.strategy == "RollingUpdate"
        assert len(deployment.conditions) == 1

    def test_deployment_info_defaults(self):
        """Test deployment info with default values"""
        deployment = DeploymentInfo(
            name="minimal-deploy", namespace="test", desired_replicas=1
        )
        assert deployment.ready_replicas == 0  # Default
        assert deployment.available_replicas == 0  # Default
        assert deployment.updated_replicas == 0  # Default
        assert deployment.strategy is None
        assert len(deployment.conditions) == 0


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


class TestLogResponse:
    """Test LogResponse model"""

    def test_log_response_complete(self, sample_log_entries):
        """Test log response with all fields"""
        response = LogResponse(
            pod_name="web-pod",
            namespace="production",
            container="nginx",
            pattern_filter="ERROR",
            total_lines=500,
            entries=sample_log_entries,
        )
        assert response.pod_name == "web-pod"
        assert response.namespace == "production"
        assert response.container == "nginx"
        assert response.pattern_filter == "ERROR"
        assert response.total_lines == 500
        assert len(response.entries) == 3

    def test_log_response_minimal(self):
        """Test log response with only required fields"""
        response = LogResponse(pod_name="simple-pod", namespace="test", total_lines=10)
        assert response.pod_name == "simple-pod"
        assert response.container is None
        assert response.pattern_filter is None
        assert len(response.entries) == 0  # Default empty list


class TestToolError:
    """Test ToolError model"""

    def test_tool_error_complete(self):
        """Test tool error with all fields"""
        error = ToolError(
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


class TestToolResult:
    """Test ToolResult model"""

    def test_tool_result_success(self, sample_pod_info):
        """Test successful tool result"""
        result = ToolResult(
            success=True,
            data=sample_pod_info,
            error=None,
            tool_name="execute_oc_get_pod",
            namespace="test-ns",
        )
        assert result.success is True
        assert result.data == sample_pod_info
        assert result.error is None
        assert result.tool_name == "execute_oc_get_pod"
        assert result.namespace == "test-ns"

    def test_tool_result_failure(self, sample_tool_error):
        """Test failed tool result"""
        result = ToolResult(
            success=False,
            data=None,
            error=sample_tool_error,
            tool_name="execute_oc_get_pod",
            namespace="test-ns",
        )
        assert result.success is False
        assert result.data is None
        assert result.error == sample_tool_error
        assert result.tool_name == "execute_oc_get_pod"

    def test_tool_result_properties(self, sample_tool_error):
        """Test ToolResult computed properties"""
        # Test non-recoverable error
        result = ToolResult(
            success=False, data=None, error=sample_tool_error, tool_name="test_tool"
        )
        assert result.is_recoverable_error is False
        assert result.error_type == ErrorType.NOT_FOUND

        # Test recoverable error
        recoverable_error = ToolError(
            type=ErrorType.TIMEOUT,
            message="Request timed out",
            recoverable=True,
            suggestion="Retry the operation",
        )
        result = ToolResult(
            success=False, data=None, error=recoverable_error, tool_name="test_tool"
        )
        assert result.is_recoverable_error is True
        assert result.error_type == ErrorType.TIMEOUT

        # Test successful result
        result = ToolResult(
            success=True, data={"test": "data"}, error=None, tool_name="test_tool"
        )
        assert result.is_recoverable_error is False
        assert result.error_type is None

    def test_tool_result_arbitrary_data_types(
        self, sample_pod_info, sample_log_response
    ):
        """Test ToolResult with different data types"""
        # Pod data
        result = ToolResult(
            success=True, data=sample_pod_info, error=None, tool_name="pod_tool"
        )
        assert isinstance(result.data, PodInfo)

        # List of pods
        result = ToolResult(
            success=True, data=[sample_pod_info], error=None, tool_name="pods_tool"
        )
        assert isinstance(result.data, list)
        assert len(result.data) == 1

        # Log response
        result = ToolResult(
            success=True, data=sample_log_response, error=None, tool_name="logs_tool"
        )
        assert isinstance(result.data, LogResponse)

        # Dictionary data
        result = ToolResult(
            success=True,
            data={"namespace": "test", "alert_name": "TestAlert"},
            error=None,
            tool_name="context_tool",
        )
        assert isinstance(result.data, dict)
        assert result.data["namespace"] == "test"

    def test_tool_result_validation_errors(self):
        """Test ToolResult validation"""
        # Missing required fields
        with pytest.raises(ValidationError):
            ToolResult()

        # Invalid success/error combination
        with pytest.raises(ValidationError):
            ToolResult(
                success=True,
                data=None,
                error=ToolError(
                    type=ErrorType.UNKNOWN,
                    message="Error",
                    recoverable=False,
                    suggestion="Fix it",
                ),
                tool_name="invalid_tool",
            )
