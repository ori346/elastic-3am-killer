"""
Tests for error handling and classification.

This module tests error classification, error suggestion generation,
and error result creation utilities.
"""

import pytest
from agents.remediation.models import ErrorType, ToolError
from agents.remediation.utils import (
    classify_oc_error,
    create_tool_error,
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
            error_type = classify_oc_error(stderr)
            assert error_type == ErrorType.NOT_FOUND, f"Failed for: {stderr}"

    def test_classify_oc_error_permission(self):
        """Test PERMISSION error classification"""
        test_cases = [
            "Forbidden: User cannot get pods in namespace production",
            "unauthorized: authentication required",
            "Error: pods is forbidden",
        ]

        for stderr in test_cases:
            error_type = classify_oc_error(stderr)
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
            error_type = classify_oc_error(stderr)
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
            error_type = classify_oc_error(stderr)
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
            error_type = classify_oc_error(stderr)
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
            error_type = classify_oc_error(stderr)
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
            error_type = classify_oc_error(stderr)
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
            error_type = classify_oc_error(stderr)
            assert error_type == ErrorType.UNKNOWN, f"Failed for: {stderr}"

    def test_classify_oc_error_case_insensitive(self):
        """Test error classification is case insensitive"""
        # Test mixed case
        error_type = classify_oc_error("ERROR: PODS NOT FOUND")
        assert error_type == ErrorType.NOT_FOUND

        # Test lowercase
        error_type = classify_oc_error("forbidden: access denied")
        assert error_type == ErrorType.PERMISSION

    @pytest.mark.parametrize(
        "stderr,expected_type",
        [
            (
                'Error from server (NotFound): pods "test" not found',
                ErrorType.NOT_FOUND,
            ),
            ("Forbidden: User cannot get pods", ErrorType.PERMISSION),
            ("Unable to connect to the server", ErrorType.NETWORK),
            ("timed out waiting", ErrorType.TIMEOUT),
            ('unknown command "invalid"', ErrorType.SYNTAX),
            ("exceeded quota", ErrorType.RESOURCE_LIMIT),
            ("configmap not found", ErrorType.CONFIGURATION),
            ("random error message", ErrorType.UNKNOWN),
        ],
    )
    def test_classify_oc_error_parametrized(self, stderr, expected_type):
        """Parametrized test for error classification"""
        result = classify_oc_error(stderr)
        assert result == expected_type


class TestErrorResultCreation:
    """Test error result creation utilities"""

    def test_create_error_result_basic(self):
        """Test basic error result creation"""
        result = create_tool_error(
            error_type=ErrorType.NOT_FOUND,
            message="Resource not found",
            tool_name="test_tool",
        )

        # Should be ToolError, not other types
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert result.message == "Resource not found"
        assert result.tool_name == "test_tool"
        assert result.recoverable is False  # Default
        assert result.suggestion != ""  # Should have auto-generated suggestion
        assert result.raw_output is None
        assert result.namespace is None

    def test_create_error_result_with_all_fields(self):
        """Test error result creation with all optional fields"""
        result = create_tool_error(
            error_type=ErrorType.TIMEOUT,
            message="Operation timed out",
            tool_name="slow_tool",
            recoverable=True,
            suggestion="Try again with longer timeout",
            raw_output="timeout occurred after 30s",
            namespace="production",
        )

        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
        assert result.message == "Operation timed out"
        assert result.tool_name == "slow_tool"
        assert result.recoverable is True
        assert result.suggestion == "Try again with longer timeout"
        assert result.raw_output == "timeout occurred after 30s"
        assert result.namespace == "production"

    def test_create_error_result_auto_suggestion(self):
        """Test that auto-suggestion works for different error types"""
        # Test each error type gets appropriate suggestion
        error_types = [
            ErrorType.NOT_FOUND,
            ErrorType.PERMISSION,
            ErrorType.TIMEOUT,
            ErrorType.NETWORK,
            ErrorType.SYNTAX,
            ErrorType.RESOURCE_LIMIT,
            ErrorType.CONFIGURATION,
            ErrorType.UNKNOWN,
        ]

        for error_type in error_types:
            result = create_tool_error(
                error_type=error_type,
                message=f"Test {error_type.value} error",
                tool_name="test_tool",
            )

            assert isinstance(result, ToolError)
            assert result.suggestion != ""  # Should have non-empty suggestion
            assert len(result.suggestion) > 10  # Should be meaningful

    def test_create_error_result_properties(self):
        """Test error result properties and validation"""
        result = create_tool_error(
            error_type=ErrorType.PERMISSION,
            message="Access denied",
            tool_name="secure_tool",
        )

        # Test that all required fields are present
        assert hasattr(result, "type")
        assert hasattr(result, "message")
        assert hasattr(result, "tool_name")
        assert hasattr(result, "recoverable")
        assert hasattr(result, "suggestion")
        assert hasattr(result, "raw_output")
        assert hasattr(result, "namespace")

        # Test that the model validates correctly
        assert result.type in ErrorType
        assert isinstance(result.message, str)
        assert isinstance(result.tool_name, str)
        assert isinstance(result.recoverable, bool)
        assert isinstance(result.suggestion, str)


class TestErrorSuggestionGeneration:
    """Test error suggestion generation"""

    def test_get_error_suggestion_not_found(self):
        """Test suggestion for NOT_FOUND errors"""
        suggestion = get_error_suggestion(ErrorType.NOT_FOUND)
        assert "verify" in suggestion.lower()
        assert "name" in suggestion.lower() or "exists" in suggestion.lower()

    def test_get_error_suggestion_permission(self):
        """Test suggestion for PERMISSION errors"""
        suggestion = get_error_suggestion(ErrorType.PERMISSION)
        assert "permission" in suggestion.lower() or "rbac" in suggestion.lower()

    def test_get_error_suggestion_timeout(self):
        """Test suggestion for TIMEOUT errors"""
        suggestion = get_error_suggestion(ErrorType.TIMEOUT)
        assert "retry" in suggestion.lower() or "again" in suggestion.lower()

    def test_get_error_suggestion_network(self):
        """Test suggestion for NETWORK errors"""
        suggestion = get_error_suggestion(ErrorType.NETWORK)
        assert "network" in suggestion.lower() or "connectivity" in suggestion.lower()

    def test_get_error_suggestion_all_types(self):
        """Test that all error types have suggestions"""
        for error_type in ErrorType:
            suggestion = get_error_suggestion(error_type)
            assert suggestion != ""
            assert len(suggestion) > 5  # Should be meaningful
            assert isinstance(suggestion, str)


class TestHelperFunctions:
    """Test helper functions used in error handling"""

    def test_extract_container_state(self):
        """Test container state extraction"""
        # Running state
        running_status = {"state": {"running": {"startedAt": "2023-01-01T10:00:00Z"}}}
        assert extract_container_state(running_status) == "running"

        # Waiting state
        waiting_status = {"state": {"waiting": {"reason": "ContainerCreating"}}}
        assert extract_container_state(waiting_status) == "waiting"

        # Terminated state
        terminated_status = {
            "state": {"terminated": {"reason": "Completed", "exitCode": 0}}
        }
        assert extract_container_state(terminated_status) == "terminated"

        # Unknown state
        empty_status = {}
        assert extract_container_state(empty_status) == "unknown"

    def test_format_ready_status(self):
        """Test ready status formatting"""
        # All containers ready
        all_ready = [
            {"name": "nginx", "ready": True},
            {"name": "sidecar", "ready": True},
        ]
        assert format_ready_status(all_ready) == "2/2"

        # Some containers ready
        partial_ready = [
            {"name": "nginx", "ready": True},
            {"name": "sidecar", "ready": False},
            {"name": "init", "ready": False},
        ]
        assert format_ready_status(partial_ready) == "1/3"

        # No containers
        no_containers = []
        assert format_ready_status(no_containers) == "0/0"

        # Missing ready field
        missing_ready = [
            {"name": "nginx"},
            {"name": "sidecar", "ready": True},
        ]
        assert format_ready_status(missing_ready) == "1/2"


class TestIntegrationErrorHandling:
    """Integration tests for error handling flows"""

    def test_full_error_flow_not_found(self):
        """Test complete error handling flow for NOT_FOUND"""
        stderr = 'Error from server (NotFound): pods "missing-pod" not found'

        # Classify error
        error_type = classify_oc_error(stderr)
        assert error_type == ErrorType.NOT_FOUND

        # Create error result
        result = create_tool_error(
            error_type=error_type,
            message=f"Pod operation failed: {stderr}",
            tool_name="oc_describe_pod",
            raw_output=stderr,
            namespace="test-namespace",
        )

        # Verify complete error result
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "missing-pod" in result.message
        assert result.tool_name == "oc_describe_pod"
        assert result.recoverable is False
        assert result.suggestion != ""
        assert stderr in result.raw_output
        assert result.namespace == "test-namespace"

    def test_full_error_flow_recoverable(self):
        """Test complete error handling flow for recoverable error"""
        stderr = "Unable to connect to the server: timeout"

        # Classify error
        error_type = classify_oc_error(stderr)
        assert error_type == ErrorType.TIMEOUT

        # Create error result with recoverable=True
        result = create_tool_error(
            error_type=error_type,
            message="Network operation timed out",
            tool_name="oc_get_pods",
            recoverable=True,  # Explicitly set as recoverable
            namespace="production",
        )

        # Verify recoverable error properties
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
        assert result.recoverable is True
        assert (
            "timeout" in result.suggestion.lower()
            or "retry" in result.suggestion.lower()
        )

    def test_error_handling_consistency_across_tools(self):
        """Test that error handling is consistent across different tools"""
        stderr = "Forbidden: User cannot list deployments"

        # Test that same error creates consistent results for different tools
        tools = [
            "oc_get_pods",
            "oc_get_deployments",
            "oc_describe_pod",
            "oc_get_logs",
        ]

        for tool_name in tools:
            error_type = classify_oc_error(stderr)
            result = create_tool_error(
                error_type=error_type,
                message=f"Tool {tool_name} failed: {stderr}",
                tool_name=tool_name,
            )

            # All should be consistent permission errors
            assert isinstance(result, ToolError)
            assert result.type == ErrorType.PERMISSION
            assert result.recoverable is False
            assert result.tool_name == tool_name
            assert "permission" in result.suggestion.lower()
