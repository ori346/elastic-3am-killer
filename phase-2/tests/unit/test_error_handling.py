"""
Tests for ToolResult error handling and classification.

This module tests error classification, error suggestion generation,
and error result creation utilities.
"""

import pytest
from agents.remediation.models import ErrorType, ToolResult
from agents.remediation.utils import (
    classify_oc_error,
    create_error_result,
    extract_container_state,
    format_ready_status,
    get_error_suggestion,
)


class TestErrorClassification:
    """Test oc command error classification"""

    def test_classify_oc_error_not_found(self):
        """Test NOT_FOUND error classification"""
        test_cases = [
            'Error from server (NotFound): pods "missing-pod" not found',
            "No resources found in namespace test",
            'deployment.apps "missing-deploy" not found',
            'error: the server doesn\'t have a resource type "invalidtype"',
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.NOT_FOUND, f"Failed for: {stderr}"

    def test_classify_oc_error_permission(self):
        """Test PERMISSION error classification"""
        test_cases = [
            "Forbidden: User cannot get pods in namespace production",
            "unauthorized: authentication required",
            "Error: pods is forbidden",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.PERMISSION, f"Failed for: {stderr}"

    def test_classify_oc_error_network(self):
        """Test NETWORK error classification"""
        test_cases = [
            "Unable to connect to the server: dial tcp: connection refused",
            "The connection to the server was refused",
            "network is unreachable",
            "network unreachable",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.NETWORK, f"Failed for: {stderr}"

    def test_classify_oc_error_timeout(self):
        """Test TIMEOUT error classification"""
        test_cases = [
            "Unable to connect to the server: timeout",
            "timed out waiting for the condition",
            "context deadline exceeded (Client.Timeout)",
            "request timeout",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.TIMEOUT, f"Failed for: {stderr}"

    def test_classify_oc_error_syntax(self):
        """Test SYNTAX error classification"""
        test_cases = [
            'error: unknown command "invalidcommand"',
            "invalid resource name syntax",
            "malformed request body",
            "error parsing resource specification",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.SYNTAX, f"Failed for: {stderr}"

    def test_classify_oc_error_resource_limit(self):
        """Test RESOURCE_LIMIT error classification"""
        test_cases = [
            "exceeded quota: compute-resources",
            "resource quota exceeded for count/pods",
            "limit range violation: cpu request exceeds limit",
            "admission webhook denied: resource limits exceeded",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.RESOURCE_LIMIT, f"Failed for: {stderr}"

    def test_classify_oc_error_configuration(self):
        """Test CONFIGURATION error classification"""
        test_cases = [
            "error validating data: invalid configuration",
            "configmap not found",
            "secret not found in configuration",
            "invalid configuration syntax",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.CONFIGURATION, f"Failed for: {stderr}"

    def test_classify_oc_error_unknown(self):
        """Test UNKNOWN error classification for unrecognized errors"""
        test_cases = [
            "Some completely random error message",
            "Internal server error occurred",
            "Unexpected error in cluster",
            "",  # Empty error message
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(1, stderr)
            assert error_type == ErrorType.UNKNOWN, f"Failed for: {stderr}"

    def test_classify_oc_error_case_insensitive(self):
        """Test error classification is case insensitive"""
        # Test mixed case
        error_type = classify_oc_error(1, "ERROR: PODS NOT FOUND")
        assert error_type == ErrorType.NOT_FOUND

        error_type = classify_oc_error(1, "CONNECTION REFUSED")
        assert error_type == ErrorType.NETWORK

    @pytest.mark.parametrize(
        "stderr,expected_type",
        [
            ("Error from server (NotFound): pods not found", ErrorType.NOT_FOUND),
            ("Forbidden: User cannot get pods", ErrorType.PERMISSION),
            ("Unable to connect to the server", ErrorType.NETWORK),
            ("timed out waiting", ErrorType.TIMEOUT),
            ("unknown command", ErrorType.SYNTAX),
            ("exceeded quota", ErrorType.RESOURCE_LIMIT),
            ("configmap not found", ErrorType.CONFIGURATION),
            ("random error message", ErrorType.UNKNOWN),
        ],
    )
    def test_classify_oc_error_parametrized(self, stderr, expected_type):
        """Test error classification using parametrized cases"""
        actual_type = classify_oc_error(1, stderr)
        assert actual_type == expected_type


class TestErrorSuggestions:
    """Test error suggestion generation"""

    def test_get_error_suggestion_not_found(self):
        """Test suggestions for NOT_FOUND errors"""
        suggestion = get_error_suggestion(ErrorType.NOT_FOUND)
        assert "resource exists" in suggestion.lower()
        assert "name" in suggestion.lower()

    def test_get_error_suggestion_not_found_with_context(self):
        """Test NOT_FOUND suggestions with namespace/resource context"""
        suggestion = get_error_suggestion(
            ErrorType.NOT_FOUND, namespace="test-ns", resource="pod"
        )
        assert "test-ns" in suggestion
        assert "pod" in suggestion or "resource" in suggestion

    def test_get_error_suggestion_permission(self):
        """Test suggestions for PERMISSION errors"""
        suggestion = get_error_suggestion(ErrorType.PERMISSION)
        assert "permission" in suggestion.lower()

    def test_get_error_suggestion_permission_with_namespace(self):
        """Test PERMISSION suggestions with namespace context"""
        suggestion = get_error_suggestion(ErrorType.PERMISSION, namespace="production")
        assert "production" in suggestion

    def test_get_error_suggestion_network(self):
        """Test suggestions for NETWORK errors"""
        suggestion = get_error_suggestion(ErrorType.NETWORK)
        assert (
            "connectivity" in suggestion.lower() or "connection" in suggestion.lower()
        )

    def test_get_error_suggestion_timeout(self):
        """Test suggestions for TIMEOUT errors"""
        suggestion = get_error_suggestion(ErrorType.TIMEOUT)
        assert "retry" in suggestion.lower() or "responsiveness" in suggestion.lower()

    def test_get_error_suggestion_syntax(self):
        """Test suggestions for SYNTAX errors"""
        suggestion = get_error_suggestion(ErrorType.SYNTAX)
        assert "syntax" in suggestion.lower() or "command" in suggestion.lower()

    def test_get_error_suggestion_resource_limit(self):
        """Test suggestions for RESOURCE_LIMIT errors"""
        suggestion = get_error_suggestion(ErrorType.RESOURCE_LIMIT)
        assert "quota" in suggestion.lower() or "limit" in suggestion.lower()

    def test_get_error_suggestion_configuration(self):
        """Test suggestions for CONFIGURATION errors"""
        suggestion = get_error_suggestion(ErrorType.CONFIGURATION)
        assert "configuration" in suggestion.lower()

    def test_get_error_suggestion_unknown(self):
        """Test suggestions for UNKNOWN errors"""
        suggestion = get_error_suggestion(ErrorType.UNKNOWN)
        assert (
            "check command logs" in suggestion.lower()
            or "cluster status" in suggestion.lower()
        )


class TestErrorResultCreation:
    """Test create_error_result utility function"""

    def test_create_error_result_basic(self):
        """Test basic error result creation"""
        result = create_error_result(
            error_type=ErrorType.NOT_FOUND,
            message="Resource not found",
            tool_name="test_tool",
        )

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.data is None
        assert result.error is not None
        assert result.error.type == ErrorType.NOT_FOUND
        assert result.error.message == "Resource not found"
        assert result.error.recoverable is False  # Default
        assert result.tool_name == "test_tool"
        assert result.namespace is None

    def test_create_error_result_with_all_fields(self):
        """Test error result creation with all optional fields"""
        result = create_error_result(
            error_type=ErrorType.TIMEOUT,
            message="Operation timed out",
            tool_name="slow_tool",
            recoverable=True,
            suggestion="Try again with longer timeout",
            raw_output="timeout: command took too long",
            namespace="test-namespace",
        )

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.error.message == "Operation timed out"
        assert result.error.recoverable is True
        assert result.error.suggestion == "Try again with longer timeout"
        assert result.error.raw_output == "timeout: command took too long"
        assert result.tool_name == "slow_tool"
        assert result.namespace == "test-namespace"

    def test_create_error_result_auto_suggestion(self):
        """Test error result with automatically generated suggestion"""
        result = create_error_result(
            error_type=ErrorType.PERMISSION,
            message="Access denied",
            tool_name="auth_tool",
            namespace="restricted",
        )

        assert result.error.suggestion is not None
        assert "permission" in result.error.suggestion.lower()
        assert "restricted" in result.error.suggestion

    def test_create_error_result_properties(self):
        """Test ToolResult properties for error results"""
        # Test non-recoverable error
        result = create_error_result(
            error_type=ErrorType.SYNTAX,
            message="Invalid command",
            tool_name="command_tool",
        )
        assert result.is_recoverable_error is False
        assert result.error_type == ErrorType.SYNTAX

        # Test recoverable error
        result = create_error_result(
            error_type=ErrorType.NETWORK,
            message="Connection failed",
            tool_name="network_tool",
            recoverable=True,
        )
        assert result.is_recoverable_error is True
        assert result.error_type == ErrorType.NETWORK


class TestUtilityFunctions:
    """Test utility functions for container and pod status"""

    def test_extract_container_state_running(self):
        """Test extracting running container state"""
        container_status = {"state": {"running": {"startedAt": "2023-01-01T10:00:00Z"}}}
        state = extract_container_state(container_status)
        assert state == "running"

    def test_extract_container_state_waiting(self):
        """Test extracting waiting container state"""
        container_status = {"state": {"waiting": {"reason": "ImagePullBackOff"}}}
        state = extract_container_state(container_status)
        assert state == "waiting"

    def test_extract_container_state_terminated(self):
        """Test extracting terminated container state"""
        container_status = {
            "state": {"terminated": {"reason": "Completed", "exitCode": 0}}
        }
        state = extract_container_state(container_status)
        assert state == "terminated"

    def test_extract_container_state_unknown(self):
        """Test extracting unknown container state"""
        container_status = {"state": {}}
        state = extract_container_state(container_status)
        assert state == "unknown"

    def test_extract_container_state_missing_state(self):
        """Test extracting state when state field is missing"""
        container_status = {}
        state = extract_container_state(container_status)
        assert state == "unknown"

    def test_format_ready_status_all_ready(self):
        """Test formatting ready status when all containers are ready"""
        container_statuses = [{"ready": True}, {"ready": True}, {"ready": True}]
        status = format_ready_status(container_statuses)
        assert status == "3/3"

    def test_format_ready_status_partial_ready(self):
        """Test formatting ready status when some containers are ready"""
        container_statuses = [{"ready": True}, {"ready": False}, {"ready": True}]
        status = format_ready_status(container_statuses)
        assert status == "2/3"

    def test_format_ready_status_none_ready(self):
        """Test formatting ready status when no containers are ready"""
        container_statuses = [{"ready": False}, {"ready": False}]
        status = format_ready_status(container_statuses)
        assert status == "0/2"

    def test_format_ready_status_empty_list(self):
        """Test formatting ready status with empty container list"""
        container_statuses = []
        status = format_ready_status(container_statuses)
        assert status == "0/0"

    def test_format_ready_status_missing_ready_field(self):
        """Test formatting ready status when ready field is missing"""
        container_statuses = [
            {"ready": True},
            {},  # Missing ready field
            {"ready": False},
        ]
        status = format_ready_status(container_statuses)
        assert status == "1/3"  # Missing ready field counts as False


class TestIntegrationErrorHandling:
    """Test integration of error handling components"""

    def test_full_error_flow_not_found(self):
        """Test complete error handling flow for NOT_FOUND"""
        stderr = 'Error from server (NotFound): pods "test-pod" not found'

        # Classify error
        error_type = classify_oc_error(1, stderr)
        assert error_type == ErrorType.NOT_FOUND

        # Create error result
        result = create_error_result(
            error_type=error_type,
            message=f"Pod not found: {stderr}",
            tool_name="execute_oc_get_pod",
            namespace="test",
            raw_output=stderr,
        )

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "test" in result.error.suggestion
        assert result.error.raw_output == stderr
        assert result.is_recoverable_error is False

    def test_full_error_flow_recoverable(self):
        """Test complete error handling flow for recoverable error"""
        stderr = "Unable to connect to the server: timeout"

        error_type = classify_oc_error(1, stderr)
        assert error_type == ErrorType.TIMEOUT

        result = create_error_result(
            error_type=error_type,
            message=f"Command timed out: {stderr}",
            tool_name="execute_oc_logs",
            recoverable=True,
            raw_output=stderr,
        )

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.is_recoverable_error is True
        assert "retry" in result.error.suggestion.lower()
        assert result.error.raw_output == stderr
