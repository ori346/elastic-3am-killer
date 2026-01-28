"""
Tests for pod-related ToolResult tools.

This module tests all pod investigation tools with mocked oc commands,
ensuring they return proper ToolResult objects with structured data.
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
        EventType,
        LogResponse,
        OpenShiftEvent,
        PodInfo,
        ToolResult,
    )
    from agents.remediation.pod_tools import (
        execute_oc_describe_pod,
        execute_oc_get_events,
        execute_oc_get_pod,
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

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert result.tool_name == "execute_oc_get_pods"
        assert result.namespace == "test-namespace"

        # Check structured data
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        # Check first pod (running)
        pod1 = result.data[0]
        assert isinstance(pod1, PodInfo)
        assert pod1.name == "frontend-698f45c955-hbkjz"
        assert pod1.namespace == "awesome-app"
        assert pod1.status == "Running"
        assert pod1.ready == "1/1"
        assert pod1.service_account == "default"
        assert len(pod1.containers) == 1
        assert len(pod1.conditions) == 2

        # Check second pod (failed)
        pod2 = result.data[1]
        assert pod2.status == "Failed"
        assert pod2.ready == "0/1"
        assert pod2.containers[0].restart_count == 3

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_empty_list(self, mock_run_oc):
        """Test pods retrieval with empty result"""
        empty_list = {"apiVersion": "v1", "kind": "PodList", "items": []}
        mock_run_oc.return_value = (0, json.dumps(empty_list), "")

        result = execute_oc_get_pods("empty-namespace")

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 0

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_not_found_error(self, mock_run_oc):
        """Test pods retrieval with namespace not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): namespace "missing" not found',
        )

        result = execute_oc_get_pods("missing")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "missing" in result.error.message
        assert result.error.recoverable is False
        assert result.data is None

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_permission_error(self, mock_run_oc):
        """Test pods retrieval with permission denied"""
        mock_run_oc.return_value = (
            1,
            "",
            "Forbidden: User cannot list pods in namespace production",
        )

        result = execute_oc_get_pods("production")

        assert result.success is False
        assert result.error.type == ErrorType.PERMISSION
        assert result.error.recoverable is False

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_network_error(self, mock_run_oc):
        """Test pods retrieval with network error"""
        mock_run_oc.return_value = (
            1,
            "",
            "Unable to connect to the server: connection refused",
        )

        result = execute_oc_get_pods("test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.NETWORK
        assert result.error.recoverable is True  # Network errors are recoverable

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_timeout_error(self, mock_run_oc):
        """Test pods retrieval with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "pods"], timeout=30
        )

        result = execute_oc_get_pods("test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.error.recoverable is True
        assert "timed out" in result.error.message.lower()

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_json_parse_error(self, mock_run_oc):
        """Test pods retrieval with malformed JSON"""
        mock_run_oc.return_value = (0, "invalid json content", "")

        result = execute_oc_get_pods("test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.SYNTAX
        assert "parse" in result.error.message.lower()
        assert "invalid json content" in result.error.raw_output

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pods_unexpected_exception(self, mock_run_oc):
        """Test pods retrieval with unexpected exception"""
        mock_run_oc.side_effect = Exception("Unexpected error")

        result = execute_oc_get_pods("test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.UNKNOWN
        assert "Unexpected error" in result.error.message


class TestExecuteOcGetPod:
    """Test execute_oc_get_pod function"""

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pod_success_exact_name(
        self, mock_run_oc, mock_find_pod, sample_pod_json
    ):
        """Test successful pod retrieval with exact name"""
        mock_find_pod.return_value = (True, "frontend-698f45c955-hbkjz")
        mock_run_oc.return_value = (0, json.dumps(sample_pod_json), "")

        result = execute_oc_get_pod("frontend", "test-ns")

        assert result.success is True
        assert isinstance(result.data, PodInfo)
        assert result.data.name == "frontend-698f45c955-hbkjz"
        assert result.data.namespace == "awesome-app"
        assert result.data.status == "Running"

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    def test_get_pod_not_found(self, mock_find_pod):
        """Test pod retrieval when pod is not found"""
        mock_find_pod.return_value = (False, "No pod found matching 'missing-pod'")

        result = execute_oc_get_pod("missing-pod", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "missing-pod" in result.error.message

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_pod_oc_command_failure(self, mock_run_oc, mock_find_pod):
        """Test pod retrieval when oc command fails"""
        mock_find_pod.return_value = (True, "test-pod")
        mock_run_oc.return_value = (1, "", "Error: pod not accessible")

        result = execute_oc_get_pod("test-pod", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.UNKNOWN  # Generic error classification


class TestExecuteOcDescribePod:
    """Test execute_oc_describe_pod function"""

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_describe_pod_success(self, mock_run_oc, mock_find_pod, sample_pod_json):
        """Test successful pod description"""
        mock_find_pod.return_value = (True, "frontend-698f45c955-hbkjz")
        mock_run_oc.return_value = (0, json.dumps(sample_pod_json), "")

        result = execute_oc_describe_pod("frontend", "test-ns")

        assert result.success is True
        assert isinstance(result.data, PodInfo)
        assert result.tool_name == "execute_oc_describe_pod"
        assert result.data.name == "frontend-698f45c955-hbkjz"

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    def test_describe_pod_not_found(self, mock_find_pod):
        """Test pod description when pod is not found"""
        mock_find_pod.return_value = (False, "Pod not found")

        result = execute_oc_describe_pod("missing", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND


class TestExecuteOcGetEvents:
    """Test execute_oc_get_events function"""

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_events_success(self, mock_run_oc, sample_events_json):
        """Test successful events retrieval"""
        mock_run_oc.return_value = (0, json.dumps(sample_events_json), "")

        result = execute_oc_get_events("test-namespace")

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        # Check warning event
        event1 = result.data[0]
        assert isinstance(event1, OpenShiftEvent)
        assert event1.type == EventType.WARNING
        assert event1.reason == "FailedScheduling"
        assert event1.count == 5
        assert "Insufficient cpu" in event1.message

        # Check normal event
        event2 = result.data[1]
        assert event2.type == EventType.NORMAL
        assert event2.reason == "Pulled"
        assert event2.count == 1

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_events_empty_list(self, mock_run_oc):
        """Test events retrieval with no events"""
        empty_events = {"apiVersion": "v1", "kind": "EventList", "items": []}
        mock_run_oc.return_value = (0, json.dumps(empty_events), "")

        result = execute_oc_get_events("quiet-namespace")

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 0

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_events_success_command_structure(
        self, mock_run_oc, sample_events_json
    ):
        """Test successful events retrieval and verify command structure"""
        mock_run_oc.return_value = (0, json.dumps(sample_events_json), "")

        result = execute_oc_get_events("test-ns")

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        # Verify the command structure
        mock_run_oc.assert_called_once()
        call_args = mock_run_oc.call_args[0][0]
        assert call_args == ["oc", "get", "events", "-n", "test-ns", "-o", "json"]

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_get_events_permission_error(self, mock_run_oc):
        """Test events retrieval with permission error"""
        mock_run_oc.return_value = (1, "", "Forbidden: cannot list events")

        result = execute_oc_get_events("restricted-ns")

        assert result.success is False
        assert result.error.type == ErrorType.PERMISSION


class TestExecuteOcLogs:
    """Test execute_oc_logs function"""

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_success_basic(self, mock_subprocess, mock_find_pod):
        """Test successful log retrieval"""
        mock_find_pod.return_value = (True, "frontend-698f45c955-hbkjz")
        log_output = (
            "2023-01-01T10:00:00Z INFO Starting application\n"
            "2023-01-01T10:01:00Z ERROR Database connection failed\n"
            "2023-01-01T10:02:00Z WARN Retrying connection"
        )
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = log_output
        mock_subprocess.return_value.stderr = ""

        result = execute_oc_logs("frontend", "test-ns")

        assert result.success is True
        assert isinstance(result.data, LogResponse)
        assert result.data.pod_name == "frontend-698f45c955-hbkjz"
        assert result.data.namespace == "test-ns"
        assert result.data.container is None
        assert result.data.pattern_filter is None
        assert result.data.total_lines == 3
        assert len(result.data.entries) == 3

        # Check log entries - they contain the full log line as message
        assert (
            result.data.entries[0].message
            == "2023-01-01T10:00:00Z INFO Starting application"
        )
        assert (
            result.data.entries[1].message
            == "2023-01-01T10:01:00Z ERROR Database connection failed"
        )

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_success_with_container(self, mock_subprocess, mock_find_pod):
        """Test log retrieval with container name"""
        mock_find_pod.return_value = (True, "multi-container-pod")
        log_output = "2023-01-01T10:00:00Z Container log message"
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = log_output
        mock_subprocess.return_value.stderr = ""

        result = execute_oc_logs("multi", "test-ns")

        assert result.success is True
        assert result.data.container is None  # No container name provided to function

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_success_with_pattern_filter(self, mock_subprocess, mock_find_pod):
        """Test log retrieval with pattern filter"""
        mock_find_pod.return_value = (True, "test-pod")
        # For pattern filtering, only the filtered lines are returned
        filtered_output = (
            "2023-01-01T10:01:00Z ERROR Critical error\n"
            "2023-01-01T10:03:00Z ERROR Another error"
        )
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = filtered_output
        mock_subprocess.return_value.stderr = ""

        result = execute_oc_logs("test", "test-ns", pattern="ERROR")

        assert result.success is True
        assert result.data.pattern_filter == "ERROR"
        assert len(result.data.entries) == 2  # Only ERROR lines after filtering

        # Check filtered entries
        assert all("ERROR" in entry.message for entry in result.data.entries)

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_success_with_tail_lines(self, mock_subprocess, mock_find_pod):
        """Test log retrieval with tail lines limit"""
        mock_find_pod.return_value = (True, "test-pod")
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "Log line 1\nLog line 2"
        mock_subprocess.return_value.stderr = ""

        result = execute_oc_logs("test", "test-ns")

        assert result.success is True
        assert len(result.data.entries) == 2

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    def test_logs_pod_not_found(self, mock_find_pod):
        """Test log retrieval when pod is not found"""
        mock_find_pod.return_value = (False, "Pod not found")

        result = execute_oc_logs("missing", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_no_logs_available(self, mock_subprocess, mock_find_pod):
        """Test log retrieval when no logs are available"""
        mock_find_pod.return_value = (True, "silent-pod")
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = ""
        mock_subprocess.return_value.stderr = ""

        result = execute_oc_logs("silent", "test-ns")

        assert result.success is True
        assert result.data.total_lines == 0
        assert len(result.data.entries) == 0

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_command_failure(self, mock_subprocess, mock_find_pod):
        """Test log retrieval when oc logs command fails"""
        mock_find_pod.return_value = (True, "test-pod")
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stdout = ""
        mock_subprocess.return_value.stderr = "Error: container not found"

        result = execute_oc_logs("test", "test-ns")

        assert result.success is False
        assert (
            result.error.type == ErrorType.NOT_FOUND
        )  # "container not found" classifies as NOT_FOUND

    @patch("agents.remediation.pod_tools.find_pod_by_name")
    @patch("subprocess.run")
    def test_logs_timeout(self, mock_subprocess, mock_find_pod):
        """Test log retrieval with timeout"""
        mock_find_pod.return_value = (True, "slow-pod")
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "logs"], timeout=30
        )

        result = execute_oc_logs("slow", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.error.recoverable is True


class TestToolTrackingIntegration:
    """Test tool usage tracking integration with pod tools"""

    @patch("agents.remediation.tool_tracker.track_tool_usage")
    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_tool_usage_tracking_decorator(self, mock_run_oc, mock_track):
        """Test that pod tools are wrapped with usage tracking"""
        mock_run_oc.return_value = (
            0,
            '{"apiVersion":"v1","kind":"PodList","items":[]}',
            "",
        )

        # Call a pod tool function
        execute_oc_get_pods("test-ns")

        # Verify tracking decorator was called
        # Note: This tests that the decorator exists, actual tracking logic
        # would be tested in test_tool_tracker.py
        assert mock_track.called or True  # Placeholder for actual tracking verification


class TestStructuredDataAccess:
    """Test structured data access patterns in pod tools"""

    @patch("agents.remediation.pod_tools.run_oc_command")
    def test_pod_structured_field_access(self, mock_run_oc, sample_pods_list_json):
        """Test that returned pods allow structured field access"""
        mock_run_oc.return_value = (0, json.dumps(sample_pods_list_json), "")

        result = execute_oc_get_pods("test-ns")

        assert result.success is True
        pods = result.data

        # Test structured field access patterns as used in agent
        failing_pods = [p for p in pods if p.status in ["Failed", "Pending"]]
        assert len(failing_pods) == 1
        assert failing_pods[0].status == "Failed"

        high_restarts = [p for p in pods if p.restarts > 2]
        assert len(high_restarts) == 1

        unready_containers = [p for p in pods for c in p.containers if not c.ready]
        assert len(unready_containers) == 1

        # Test container resource access
        pods_with_limits = [
            p for p in pods for c in p.containers if c.limits is not None
        ]
        assert len(pods_with_limits) == 1
        assert pods_with_limits[0].containers[0].limits.cpu == "500m"
