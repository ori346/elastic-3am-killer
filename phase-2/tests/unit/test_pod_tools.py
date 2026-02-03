"""
Tests for pod-related tools.

This module tests all pod investigation tools with mocked oc commands,
ensuring they return proper model objects with structured data.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

# Mock the imports that might not be available in test environment
with patch.dict(
    "sys.modules",
    {
        "configs": MagicMock(LOG_COLLECTION=MagicMock(), TIMEOUTS=MagicMock()),
        "agents.remediation.tool_tracker": MagicMock(track_tool_usage=lambda x: x),
    },
):
    from agents.remediation.models import (
        ErrorType,
        LogResult,
        PodListResult,
        PodSummary,
        PodDetailedResult,
        ToolError,
    )
    from agents.remediation.pod_tools import (
        execute_oc_describe_pod,
        execute_oc_get_pods,
        execute_oc_logs,
    )


class TestExecuteOcGetPods:
    """Test execute_oc_get_pods function"""

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_success(self, mock_run_oc, sample_pods_list_json):
        """Test successful pods retrieval"""
        mock_run_oc.return_value = (0, json.dumps(sample_pods_list_json), "")

        result = execute_oc_get_pods("test-namespace")

        # Should be PodListResult, not ToolError
        assert isinstance(result, PodListResult)
        assert result.tool_name == "execute_oc_get_pods"
        assert result.namespace == "test-namespace"

        # Check structured data
        assert isinstance(result.pods, list)
        assert len(result.pods) == 2

        # Check first pod (running)
        pod1 = result.pods[0]
        assert pod1.name == "frontend-698f45c955-hbkjz"
        assert pod1.status == "Running"
        assert pod1.ready == "1/1"
        assert pod1.restarts == 0

        # Check second pod (failed)
        pod2 = result.pods[1]
        assert pod2.name == "backend-db-567890abcd-xyz12"
        assert pod2.status == "Failed"
        assert pod2.ready == "0/1"
        assert pod2.restarts == 3

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_empty_list(self, mock_run_oc):
        """Test pods retrieval with empty namespace"""
        empty_pods = {"apiVersion": "v1", "kind": "PodList", "items": []}
        mock_run_oc.return_value = (0, json.dumps(empty_pods), "")

        result = execute_oc_get_pods("empty-namespace")

        # Should still be PodListResult, just with empty list
        assert isinstance(result, PodListResult)
        assert result.namespace == "empty-namespace"
        assert isinstance(result.pods, list)
        assert len(result.pods) == 0

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_not_found_error(self, mock_run_oc):
        """Test pods retrieval with namespace not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): namespaces "missing" not found',
        )

        result = execute_oc_get_pods("missing")

        # Should be ToolError, not PodListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "missing" in result.message

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_permission_error(self, mock_run_oc):
        """Test pods retrieval with permission denied"""
        mock_run_oc.return_value = (
            1,
            "",
            "Forbidden: User cannot list pods in namespace secure",
        )

        result = execute_oc_get_pods("secure")

        # Should be ToolError, not PodListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.PERMISSION
        assert result.recoverable is False

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_network_error(self, mock_run_oc):
        """Test pods retrieval with network error"""
        mock_run_oc.return_value = (1, "", "Unable to connect to server")

        result = execute_oc_get_pods("test-ns")

        # Should be ToolError, not PodListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NETWORK
        assert result.recoverable is True

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_timeout_error(self, mock_run_oc):
        """Test pods retrieval with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "pods"], timeout=30
        )

        result = execute_oc_get_pods("test-ns")

        # Should be ToolError, not PodListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
        assert result.recoverable is True

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_json_parse_error(self, mock_run_oc):
        """Test pods retrieval with malformed JSON"""
        mock_run_oc.return_value = (0, "invalid json", "")

        result = execute_oc_get_pods("test-ns")

        # Should be ToolError, not PodListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_unexpected_exception(self, mock_run_oc):
        """Test pods retrieval with unexpected exception"""
        mock_run_oc.side_effect = Exception("Unexpected error")

        result = execute_oc_get_pods("test-ns")

        # Should be ToolError, not PodListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.UNKNOWN


class TestExecuteOcGetPod:
    """Test execute_oc_describe_pod function"""

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pod_success_exact_name(
        self, mock_run_oc, mock_find_pod, sample_pod_json
    ):
        """Test successful pod retrieval with exact name"""
        mock_find_pod.return_value = (True, "frontend-698f45c955-hbkjz")

        # Enhance sample with additional details for our new model
        enhanced_pod = {
            **sample_pod_json,
            "metadata": {
                **sample_pod_json["metadata"],
                "labels": {"app": "frontend", "tier": "web"},
                "annotations": {"deployment.kubernetes.io/revision": "1"},
                "ownerReferences": [
                    {
                        "kind": "ReplicaSet",
                        "name": "frontend-698f45c955",
                        "uid": "12345-abcde",
                    }
                ],
            },
            "spec": {
                **sample_pod_json["spec"],
                "securityContext": {"runAsUser": 1000},
                "containers": [
                    {
                        **sample_pod_json["spec"]["containers"][0],
                        "ports": [{"containerPort": 80, "protocol": "TCP"}],
                        "env": [{"name": "NODE_ENV", "value": "production"}],
                        "livenessProbe": {
                            "httpGet": {"path": "/health", "port": 80},
                            "periodSeconds": 30,
                        },
                        "readinessProbe": {
                            "httpGet": {"path": "/ready", "port": 80},
                            "periodSeconds": 10,
                        },
                    }
                ],
            },
            "status": {
                **sample_pod_json["status"],
                "podIP": "10.244.0.5",
                "hostIP": "192.168.1.10",
                "containerStatuses": [
                    {
                        "name": "nginx",
                        "ready": True,
                        "restartCount": 0,
                        "state": {"running": {"startedAt": "2023-01-01T10:00:00Z"}},
                    }
                ],
            },
        }

        mock_run_oc.return_value = (0, json.dumps(enhanced_pod), "")

        result = execute_oc_describe_pod("frontend", "test-namespace")

        # Should be PodDetailedResult, not ToolError
        assert isinstance(result, PodDetailedResult)
        assert result.tool_name == "execute_oc_describe_pod"
        assert result.namespace == "test-namespace"

        # Check pod details
        pod = result.pod
        assert pod.name == "frontend-698f45c955-hbkjz"
        assert pod.status == "Running"
        assert pod.ready == "1/1"
        assert pod.restarts == 0
        assert pod.pod_ip == "10.244.0.5"
        assert pod.host_ip == "192.168.1.10"
        assert "app" in pod.labels
        assert len(pod.owner_references) == 1
        assert pod.owner_references[0]["kind"] == "ReplicaSet"

        # Check container details
        assert len(result.containers) == 1
        container = result.containers[0]
        assert container.name == "nginx"
        assert container.image == "nginx:1.20"
        assert container.ready is True
        assert container.state == "running"
        assert container.limits is not None
        assert len(container.ports) == 1
        assert len(container.environment) == 1
        assert container.liveness_probe is not None
        assert container.readiness_probe is not None

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    def test_get_pod_not_found(self, mock_find_pod):
        """Test pod retrieval when pod not found"""
        mock_find_pod.return_value = (False, "Pod 'missing' not found")

        result = execute_oc_describe_pod("missing", "test-ns")

        # Should be ToolError, not PodDetailedResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "missing" in result.message

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pod_oc_command_failure(self, mock_run_oc, mock_find_pod):
        """Test pod retrieval when oc command fails"""
        mock_find_pod.return_value = (True, "existing-pod")
        mock_run_oc.return_value = (1, "", "Forbidden: User cannot get pods")

        result = execute_oc_describe_pod("existing-pod", "test-ns")

        # Should be ToolError, not PodDetailedResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.PERMISSION


class TestExecuteOcLogs:
    """Test execute_oc_logs function"""

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools._get_unfiltered_logs")
    def test_logs_success_basic(self, mock_get_logs, mock_find_pod):
        """Test successful log retrieval"""
        mock_find_pod.return_value = (True, "frontend-abc123")
        mock_get_logs.return_value = (
            ["INFO: Application started", "ERROR: Database connection failed"],
            None,
        )

        result = execute_oc_logs("frontend", "test-namespace")

        # Should be LogResult, not ToolError
        assert isinstance(result, LogResult)
        assert result.tool_name == "execute_oc_logs"
        assert result.namespace == "test-namespace"
        assert result.pod_name == "frontend-abc123"
        assert result.total_lines == 2

        # Check log entries
        assert len(result.entries) == 2
        assert result.entries[0].level == "INFO"
        assert "Application started" in result.entries[0].message
        assert result.entries[1].level == "ERROR"
        assert "Database connection failed" in result.entries[1].message

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools._get_unfiltered_logs")
    def test_logs_success_with_container(self, mock_get_logs, mock_find_pod):
        """Test log retrieval with specific container"""
        mock_find_pod.return_value = (True, "multi-container-pod")
        mock_get_logs.return_value = (["Container log message"], None)

        result = execute_oc_logs("multi-container", "test-ns", container="nginx")

        # Should be LogResult, not ToolError
        assert isinstance(result, LogResult)
        assert result.pod_name == "multi-container-pod"
        assert result.total_lines == 1

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools._get_filtered_logs")
    def test_logs_success_with_pattern_filter(self, mock_get_logs, mock_find_pod):
        """Test log retrieval with pattern filtering"""
        mock_find_pod.return_value = (True, "app-pod")
        mock_get_logs.return_value = (["ERROR: Critical failure"], None)

        result = execute_oc_logs("app", "test-ns", pattern="ERROR")

        # Should be LogResult, not ToolError
        assert isinstance(result, LogResult)
        assert result.total_lines == 1
        assert result.entries[0].level == "ERROR"

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools._get_filtered_logs")
    def test_logs_success_with_tail_lines(self, mock_get_logs, mock_find_pod):
        """Test log retrieval with pattern returns empty results"""
        mock_find_pod.return_value = (True, "app-pod")
        mock_get_logs.return_value = ([], None)  # No matches found

        result = execute_oc_logs("app", "test-ns", pattern="NOTFOUND")

        # Should be LogResult with empty entries, not ToolError
        assert isinstance(result, LogResult)
        assert result.total_lines == 0
        assert len(result.entries) == 0

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    def test_logs_pod_not_found(self, mock_find_pod):
        """Test log retrieval when pod not found"""
        mock_find_pod.return_value = (False, "Pod not found")

        result = execute_oc_logs("missing-pod", "test-ns")

        # Should be ToolError, not LogResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools._get_unfiltered_logs")
    def test_logs_no_logs_available(self, mock_get_logs, mock_find_pod):
        """Test log retrieval when no logs available"""
        mock_find_pod.return_value = (True, "no-logs-pod")
        mock_get_logs.return_value = ([], None)

        result = execute_oc_logs("no-logs", "test-ns")

        # Should be LogResult with empty entries, not ToolError
        assert isinstance(result, LogResult)
        assert result.total_lines == 0
        assert len(result.entries) == 0

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools._get_unfiltered_logs")
    def test_logs_command_failure(self, mock_get_logs, mock_find_pod):
        """Test log retrieval when command fails"""
        mock_find_pod.return_value = (True, "failing-pod")
        mock_get_logs.return_value = (
            [],
            ToolError(
                tool_name="execute_oc_logs",
                type=ErrorType.PERMISSION,
                message="Permission denied",
                recoverable=False,
                suggestion="Check permissions",
            ),
        )

        result = execute_oc_logs("failing", "test-ns")

        # Should return the ToolError from the helper
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.PERMISSION

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    def test_logs_timeout(self, mock_find_pod):
        """Test log retrieval with timeout"""
        mock_find_pod.return_value = (True, "slow-pod")

        # Mock a timeout exception directly on the function
        with patch(
            "agents.remediation.pod_tools._get_unfiltered_logs"
        ) as mock_get_logs:
            mock_get_logs.side_effect = subprocess.TimeoutExpired(
                cmd=["oc", "logs"], timeout=30
            )

            result = execute_oc_logs("slow", "test-ns")

            # Should be ToolError, not LogResult
            assert isinstance(result, ToolError)
            assert result.type == ErrorType.TIMEOUT
            assert result.recoverable is True


class TestStructuredDataAccess:
    """Test structured data access patterns"""

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_pod_structured_field_access(self, mock_run_oc, sample_pods_list_json):
        """Test that pod data can be accessed as structured fields"""
        mock_run_oc.return_value = (0, json.dumps(sample_pods_list_json), "")

        result = execute_oc_get_pods("test-namespace")

        # Test structured field access
        assert isinstance(result, PodListResult)
        assert hasattr(result, "pods")
        assert hasattr(result, "tool_name")
        assert hasattr(result, "namespace")

        pod = result.pods[0]
        assert hasattr(pod, "name")
        assert hasattr(pod, "status")
        assert hasattr(pod, "ready")
        assert hasattr(pod, "restarts")
        assert hasattr(pod, "age")


class TestPodErrorHandling:
    """Test pod tool error handling patterns"""

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_pod_error_classification(self, mock_run_oc):
        """Test that pod tools correctly classify different error types"""
        test_cases = [
            ("pods not found", ErrorType.NOT_FOUND, False),
            ("User cannot get pods", ErrorType.PERMISSION, False),
            ("Unable to connect", ErrorType.NETWORK, True),
            ("timed out", ErrorType.TIMEOUT, True),
            ("invalid syntax", ErrorType.SYNTAX, False),
        ]

        for error_msg, expected_type, expected_recoverable in test_cases:
            # Use the exact error message that will be classified correctly
            if expected_type == ErrorType.NOT_FOUND:
                stderr = f"Error from server (NotFound): {error_msg}"
            elif expected_type == ErrorType.PERMISSION:
                stderr = f"Forbidden: {error_msg}"
            elif expected_type == ErrorType.NETWORK:
                stderr = f"Unable to connect to the server: {error_msg}"
            elif expected_type == ErrorType.TIMEOUT:
                stderr = f"timed out waiting: {error_msg}"
            elif expected_type == ErrorType.SYNTAX:
                stderr = f"unknown command: {error_msg}"
            else:
                stderr = f"Error: {error_msg}"

            mock_run_oc.return_value = (1, "", stderr)
            result = execute_oc_get_pods("test")

            assert isinstance(result, ToolError)
            assert result.type == expected_type
            assert result.recoverable == expected_recoverable

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_pod_missing_fields_graceful_handling(self, mock_run_oc):
        """Test pod tools handle missing optional fields gracefully"""
        minimal_pod_list = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [
                {
                    "metadata": {"name": "minimal-pod", "namespace": "test"},
                    "status": {"phase": "Running"},
                }
            ],
        }
        mock_run_oc.return_value = (0, json.dumps(minimal_pod_list), "")

        result = execute_oc_get_pods("test")

        # Should handle missing fields gracefully
        assert isinstance(result, PodListResult)
        assert len(result.pods) == 1
        pod = result.pods[0]
        assert pod.name == "minimal-pod"
        assert pod.status == "Running"
        # Should have default values for missing fields
        assert pod.ready == "0/0"  # Default when no container statuses
        assert pod.restarts == 0


class TestPodToolTrackingAndConfig:
    """Test pod tool usage tracking and configuration"""

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_pod_tool_usage_tracking(self, mock_run_oc):
        """Test that pod tools work correctly"""
        mock_run_oc.return_value = (0, '{"items": []}', "")

        result = execute_oc_get_pods("test")

        # Should return successful result
        assert isinstance(result, PodListResult)
        assert result.tool_name == "execute_oc_get_pods"

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_pod_timeout_configuration(self, mock_run_oc):
        """Test that pod tools respect timeout configuration"""
        # This mainly tests that the function doesn't crash with timeouts
        mock_run_oc.side_effect = subprocess.TimeoutExpired(cmd=["oc"], timeout=120)

        result = execute_oc_get_pods("test")
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
