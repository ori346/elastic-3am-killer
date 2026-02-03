"""
Shared pytest fixtures for ToolResult system testing.

This module provides fixtures for testing the OpenShift remediation tools
without requiring actual cluster access or subprocess calls.
"""

from unittest.mock import AsyncMock

import pytest
from agents.remediation.models import (
    DeploymentCondition,
    ErrorType,
    LogEntry,
    ToolError,
    PodSummary,
    LogResult,
)


# Reset tool usage counter before each test
@pytest.fixture(autouse=True)
def reset_tool_usage():
    """Reset tool usage counter before each test"""
    try:
        from agents.remediation.tool_tracker import reset_tool_usage_counter

        reset_tool_usage_counter()
        yield
    except ImportError:
        # If tool tracker doesn't exist, just continue
        yield


# ===== Mock Data Fixtures =====


@pytest.fixture
def sample_pod_json():
    """Sample OpenShift pod JSON response"""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "frontend-698f45c955-hbkjz", "namespace": "awesome-app"},
        "spec": {
            "serviceAccountName": "default",
            "containers": [
                {
                    "name": "nginx",
                    "image": "nginx:1.20",
                    "resources": {
                        "limits": {"cpu": "500m", "memory": "256Mi"},
                        "requests": {"cpu": "200m", "memory": "128Mi"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "nginx",
                    "ready": True,
                    "restartCount": 0,
                    "state": {"running": {"startedAt": "2023-01-01T10:00:00Z"}},
                }
            ],
            "conditions": [
                {"type": "Ready", "status": "True", "reason": "PodReady"},
                {"type": "PodScheduled", "status": "True"},
            ],
        },
    }


@pytest.fixture
def sample_pods_list_json():
    """Sample OpenShift pods list JSON response"""
    return {
        "apiVersion": "v1",
        "kind": "PodList",
        "items": [
            {
                "metadata": {
                    "name": "frontend-698f45c955-hbkjz",
                    "namespace": "awesome-app",
                },
                "spec": {
                    "serviceAccountName": "default",
                    "containers": [
                        {
                            "name": "nginx",
                            "image": "nginx:1.20",
                            "resources": {
                                "limits": {"cpu": "500m", "memory": "256Mi"},
                                "requests": {"cpu": "200m", "memory": "128Mi"},
                            },
                        }
                    ],
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {
                            "name": "nginx",
                            "ready": True,
                            "restartCount": 0,
                            "state": {"running": {"startedAt": "2023-01-01T10:00:00Z"}},
                        }
                    ],
                    "conditions": [
                        {"type": "Ready", "status": "True", "reason": "PodReady"},
                        {"type": "PodScheduled", "status": "True"},
                    ],
                },
            },
            {
                "metadata": {
                    "name": "backend-db-567890abcd-xyz12",
                    "namespace": "awesome-app",
                },
                "spec": {
                    "serviceAccountName": "backend-sa",
                    "containers": [
                        {
                            "name": "postgres",
                            "image": "postgres:13",
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "64Mi"}
                            },
                        }
                    ],
                },
                "status": {
                    "phase": "Failed",
                    "containerStatuses": [
                        {
                            "name": "postgres",
                            "ready": False,
                            "restartCount": 3,
                            "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                        }
                    ],
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "False",
                            "reason": "ContainersNotReady",
                        }
                    ],
                },
            },
        ],
    }


@pytest.fixture
def sample_deployment_json():
    """Sample OpenShift deployment JSON response"""
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "frontend", "namespace": "awesome-app"},
        "spec": {"replicas": 3, "strategy": {"type": "RollingUpdate"}},
        "status": {
            "replicas": 3,
            "readyReplicas": 2,
            "availableReplicas": 2,
            "updatedReplicas": 3,
            "conditions": [
                {
                    "type": "Available",
                    "status": "True",
                    "reason": "MinimumReplicasAvailable",
                    "message": "Deployment has minimum availability.",
                },
                {
                    "type": "Progressing",
                    "status": "False",
                    "reason": "ProgressDeadlineExceeded",
                    "message": "ReplicaSet has not made progress",
                },
            ],
        },
    }


@pytest.fixture
def sample_events_json():
    """Sample OpenShift events JSON response"""
    return {
        "apiVersion": "v1",
        "kind": "EventList",
        "items": [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/3 nodes are available: 3 Insufficient cpu.",
                "involvedObject": {"name": "backend-db"},
                "count": 5,
                "firstTimestamp": "2023-01-01T10:00:00Z",
                "lastTimestamp": "2023-01-01T10:05:00Z",
            },
            {
                "type": "Normal",
                "reason": "Pulled",
                "message": "Successfully pulled image",
                "involvedObject": {"name": "frontend"},
                "count": 1,
                "firstTimestamp": "2023-01-01T10:01:00Z",
                "lastTimestamp": "2023-01-01T10:01:00Z",
            },
        ],
    }


# ===== Model Instance Fixtures =====




@pytest.fixture
def sample_deployment_condition():
    """Sample DeploymentCondition instance"""
    return DeploymentCondition(
        type="Available",
        status="True",
        reason="MinimumReplicasAvailable",
        message="Deployment has minimum availability.",
    )


@pytest.fixture
def sample_log_entries():
    """Sample LogEntry instances"""
    return [
        LogEntry(level="INFO", message="Application started"),
        LogEntry(
            level="ERROR", message="Database connection failed", container="backend"
        ),
        LogEntry(message="Debug message"),
    ]


@pytest.fixture
def sample_tool_error():
    """Sample ToolError instance"""
    return ToolError(
        tool_name="test_tool",
        type=ErrorType.NOT_FOUND,
        message="Resource not found",
        recoverable=False,
        suggestion="Check resource name and namespace",
    )


@pytest.fixture
def sample_pod_info():
    """Sample PodSummary instance for legacy tests"""
    return PodSummary(
        name="frontend-abc123",
        status="Running",
        ready="1/1",
        restarts=0,
        age="5m",
    )


@pytest.fixture
def sample_log_response():
    """Sample LogResult instance for legacy tests"""
    return LogResult(
        tool_name="execute_oc_logs",
        namespace="test",
        pod_name="test-pod",
        total_lines=3,
        entries=[
            LogEntry(level="INFO", message="App started"),
            LogEntry(level="ERROR", message="Connection failed"),
            LogEntry(message="Debug info"),
        ],
    )


# ===== Mock Infrastructure Fixtures =====


class MockEditState:
    """Mock context edit state that implements async context manager protocol"""

    def __init__(self):
        self.data = {"state": {}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value


@pytest.fixture
def mock_context():
    """Mock LlamaIndex context for testing context tools"""
    mock = AsyncMock()

    # Mock store with get method
    mock.store.get = AsyncMock(
        side_effect=lambda key: {
            "alert_data": {"alert": "test alert"},
            "namespace": "test-namespace",
            "alert_name": "TestAlert",
            "alert_diagnostics": "Test diagnostics",
            "alert_status": "firing",
            "recommendation": "Test recommendation",
        }.get(key)
    )

    # Mock store with put method
    mock.store.put = AsyncMock()

    # Mock store with edit_state method that returns an async context manager
    def edit_state_func():
        return MockEditState()
    mock.store.edit_state = edit_state_func

    return mock


@pytest.fixture
def pod_name_matching_cases():
    """Test cases for pod name matching"""
    return [
        ("frontend", "frontend-698f45c955-hbkjz"),
        ("backend", "backend-db-567890abcd-xyz12"),
        ("no-match", None),
    ]


@pytest.fixture
def error_classification_cases():
    """Test cases for error classification"""
    return [
        ("Error from server (NotFound): pods not found", ErrorType.NOT_FOUND),
        ("Forbidden: User cannot get pods", ErrorType.PERMISSION),
        ("Unable to connect to the server", ErrorType.NETWORK),
        ("timed out waiting", ErrorType.TIMEOUT),
        ("unknown command", ErrorType.SYNTAX),
        ("exceeded quota", ErrorType.RESOURCE_LIMIT),
        ("configmap not found", ErrorType.CONFIGURATION),
        ("random error message", ErrorType.UNKNOWN),
    ]
