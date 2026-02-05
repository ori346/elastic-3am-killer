"""
Tests for context management tools.

This module tests context tools that read and write alert diagnostics
and remediation plans using mocked LlamaIndex Context.
"""

from unittest.mock import AsyncMock

import pytest
from agents.remediation.context_tools import (
    READ_ONLY_OC_COMMANDS,
    read_alert_diagnostics_data,
    write_remediation_plan,
)
from agents.remediation.models import (
    ErrorType,
    AlertDiagnosticsResult,
    RemediationPlanResult,
    ToolError,
)


class MockEditState:
    """Helper class for mocking async context managers"""

    def __init__(self):
        self.state = {"state": {}}

    def __getitem__(self, key):
        return self.state[key]

    def __setitem__(self, key, value):
        self.state[key] = value

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class MockAsyncContextManager:
    """Helper class for mocking async context managers"""

    def __init__(self, return_value=None):
        self.return_value = return_value or MockEditState()

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class TestReadAlertDiagnosticsData:
    """Test read_alert_diagnostics_data function"""

    @pytest.mark.asyncio
    async def test_read_alert_data_success(self, mock_context):
        """Test successful alert diagnostics reading"""
        # Mock context store with complete alert data
        mock_context.store.get = AsyncMock(
            return_value={
                "namespace": "production",
                "alert_name": "PodCrashLoopBackOff",
                "alert_diagnostics": "Pod backend-db is crashing repeatedly due to memory issues",
                "alert_status": "firing",
                "recommendation": "Increase memory limits and check application logs",
            }
        )

        result = await read_alert_diagnostics_data(mock_context)

        # Should be AlertDiagnosticsResult, not ToolError
        assert isinstance(result, AlertDiagnosticsResult)
        assert result.tool_name == "read_alert_diagnostics_data"
        assert result.namespace == "production"

        # Check structured data
        assert isinstance(result.alert_diagnostics, dict)
        data = result.alert_diagnostics
        assert data["namespace"] == "production"
        assert data["alert_name"] == "PodCrashLoopBackOff"
        assert "memory issues" in data["alert_diagnostics"]
        assert data["alert_status"] == "firing"
        assert "memory limits" in data["recommendation"]

    @pytest.mark.asyncio
    async def test_read_alert_data_missing_state(self, mock_context):
        """Test reading alert data when state is missing"""
        mock_context.store.get = AsyncMock(return_value=None)

        result = await read_alert_diagnostics_data(mock_context)

        # Should be ToolError, not AlertDiagnosticsResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "No alert diagnostics data found" in result.message
        assert "shared context" in result.message
        assert "namespace, alert name" in result.message
        assert "Workflow Coordinator" in result.suggestion

    @pytest.mark.asyncio
    async def test_read_alert_data_invalid_state_type(self, mock_context):
        """Test reading alert data when state is not a dict"""
        mock_context.store.get = AsyncMock(return_value="invalid_state_type")

        result = await read_alert_diagnostics_data(mock_context)

        # Should be ToolError, not AlertDiagnosticsResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "shared context" in result.message

    @pytest.mark.asyncio
    async def test_read_alert_data_incomplete_data(self, mock_context):
        """Test reading alert data with missing critical fields"""
        mock_context.store.get = AsyncMock(
            return_value={
                "alert_diagnostics": "Some diagnostics",
                "alert_status": "firing",
                # Missing namespace and alert_name
            }
        )

        result = await read_alert_diagnostics_data(mock_context)

        # Should be ToolError, not AlertDiagnosticsResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "incomplete" in result.message.lower()
        assert "namespace and alert name" in result.message
        assert "Cannot target remediation efforts" in result.message

    @pytest.mark.asyncio
    async def test_read_alert_data_with_defaults(self, mock_context):
        """Test reading alert data that uses default values"""
        mock_context.store.get = AsyncMock(
            return_value={
                "namespace": "test-ns",
                "alert_name": "TestAlert",
                # Missing optional fields - should use defaults
            }
        )

        result = await read_alert_diagnostics_data(mock_context)

        # Should be AlertDiagnosticsResult, not ToolError
        assert isinstance(result, AlertDiagnosticsResult)
        data = result.alert_diagnostics
        assert data["namespace"] == "test-ns"
        assert data["alert_name"] == "TestAlert"
        assert data["alert_diagnostics"] == ""  # Default
        assert data["alert_status"] == "unknown"  # Default
        assert data["recommendation"] == ""  # Default

    @pytest.mark.asyncio
    async def test_read_alert_data_context_exception(self, mock_context):
        """Test reading alert data when context store throws exception"""
        mock_context.store.get = AsyncMock(side_effect=Exception("Context error"))

        result = await read_alert_diagnostics_data(mock_context)

        # Should be ToolError, not AlertDiagnosticsResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.UNKNOWN
        assert "Context error" in result.message


class TestWriteRemediationPlan:
    """Test write_remediation_plan function"""

    @pytest.mark.asyncio
    async def test_write_plan_success(self, mock_context):
        """Test successful remediation plan writing"""
        # The mock_context fixture handles the edit_state setup

        # Use actual remediation commands, not investigation commands
        commands = [
            "oc set resources deployment crashed-app --limits=memory=512Mi",
            "oc scale deployment crashed-app --replicas=3",
        ]

        result = await write_remediation_plan(
            mock_context, "Test explanation", commands
        )

        # Should be RemediationPlanResult, not ToolError
        assert isinstance(result, RemediationPlanResult)
        assert result.tool_name == "write_remediation_plan"
        assert result.plan_written is True
        assert "Workflow Coordinator" in result.next_step

        # Context was successfully used (no exception means success)

    @pytest.mark.asyncio
    async def test_write_plan_no_commands(self, mock_context):
        """Test writing plan with no commands"""
        result = await write_remediation_plan(mock_context, "Test explanation", [])

        # Should be ToolError, not RemediationPlanResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX
        assert "No remediation commands provided" in result.message
        assert "executable actions" in result.message

    @pytest.mark.asyncio
    async def test_write_plan_read_only_commands(self, mock_context):
        """Test writing plan with only read-only commands"""
        commands = ["oc get pods", "oc describe deployment"]  # All read-only

        result = await write_remediation_plan(
            mock_context, "Test explanation", commands
        )

        # Should be ToolError, not RemediationPlanResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX
        assert "Read-only commands cannot remediate alerts" in result.message
        assert (
            "oc get pods" in result.message
            or "oc describe deployment" in result.message
        )

    @pytest.mark.asyncio
    async def test_write_plan_mixed_commands(self, mock_context):
        """Test writing plan with mixed read-only and remediation commands"""
        mock_edit = MockEditState()
        mock_context.store.edit_state = AsyncMock(return_value=mock_edit)

        commands = [
            "oc get pods",  # read-only - would be rejected
            "oc patch deployment app --patch='...'",  # remediation command
            "oc scale deployment app --replicas=2",  # remediation command
        ]

        # The current implementation rejects ANY read-only commands, so this will fail
        result = await write_remediation_plan(
            mock_context, "Test explanation", commands
        )

        # Should be ToolError because it contains read-only commands
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX
        assert "Read-only commands cannot remediate alerts" in result.message

    @pytest.mark.asyncio
    async def test_write_plan_context_exception(self, mock_context):
        """Test writing plan when context throws exception"""

        # Override edit_state to raise an exception
        def failing_edit_state():
            raise Exception("Context write error")

        mock_context.store.edit_state = failing_edit_state

        # Use valid remediation commands
        commands = ["oc scale deployment test --replicas=1"]

        result = await write_remediation_plan(
            mock_context, "Test explanation", commands
        )

        # Should be ToolError, not RemediationPlanResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.UNKNOWN
        assert "Context write error" in result.message

    @pytest.mark.asyncio
    async def test_write_plan_command_filtering(self, mock_context):
        """Test that read-only commands are properly rejected"""
        mock_edit = MockEditState()
        mock_context.store.edit_state = AsyncMock(return_value=mock_edit)

        # Mix of remediation and read-only commands
        commands = [
            "oc patch deployment failing-app --patch='...'",  # remediation
            "oc get pods",  # read-only
            "oc get deployments",  # read-only
            "oc scale deployment failing-app --replicas=2",  # remediation
            "oc get events",  # read-only
        ]

        result = await write_remediation_plan(
            mock_context, "Test explanation", commands
        )

        # Should be ToolError because it contains read-only commands
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX
        assert "Read-only commands cannot remediate alerts" in result.message

    @pytest.mark.asyncio
    async def test_write_plan_duplicate_command_handling(self, mock_context):
        """Test handling of duplicate commands"""
        # The mock_context fixture handles the edit_state setup

        commands = [
            "oc scale deployment test-app --replicas=2",
            "oc set resources deployment test-app --limits=memory=256Mi",
            "oc scale deployment test-app --replicas=2",  # Duplicate
            "oc set resources deployment test-app --limits=memory=256Mi",  # Duplicate
        ]

        result = await write_remediation_plan(
            mock_context, "Test explanation", commands
        )

        # Should be RemediationPlanResult, not ToolError
        assert isinstance(result, RemediationPlanResult)
        assert result.plan_written is True
        # Should handle duplicates gracefully


class TestContextToolsIntegration:
    """Integration tests for context tools"""

    @pytest.mark.asyncio
    async def test_context_tools_error_handling_consistency(self, mock_context):
        """Test that context tools handle errors consistently"""
        # Test that both tools return ToolError for similar failure scenarios
        mock_context.store.get = AsyncMock(side_effect=Exception("Test error"))
        mock_context.store.edit_state = AsyncMock(side_effect=Exception("Test error"))

        read_result = await read_alert_diagnostics_data(mock_context)
        write_result = await write_remediation_plan(
            mock_context, "Test explanation", ["oc scale deployment test --replicas=1"]
        )

        # Both should be ToolError with UNKNOWN type
        assert isinstance(read_result, ToolError)
        assert isinstance(write_result, ToolError)
        assert read_result.type == ErrorType.UNKNOWN
        assert write_result.type == ErrorType.UNKNOWN

    @pytest.mark.asyncio
    async def test_context_tools_structured_data_access(self, mock_context):
        """Test that context tools provide structured data access"""
        # Test read function
        mock_context.store.get = AsyncMock(
            return_value={
                "namespace": "test",
                "alert_name": "TestAlert",
                "alert_diagnostics": "Test diagnostics",
            }
        )

        read_result = await read_alert_diagnostics_data(mock_context)
        assert isinstance(read_result, AlertDiagnosticsResult)
        assert hasattr(read_result, "alert_diagnostics")
        assert hasattr(read_result, "tool_name")
        assert hasattr(read_result, "namespace")

        # Test write function - mock_context fixture handles edit_state setup

        write_result = await write_remediation_plan(
            mock_context, "Test explanation", ["oc rollout restart deployment/test"]
        )
        assert isinstance(write_result, RemediationPlanResult)
        assert hasattr(write_result, "plan_written")
        assert hasattr(write_result, "next_step")
        assert hasattr(write_result, "tool_name")


class TestReadOnlyCommandsConstant:
    """Test the READ_ONLY_OC_COMMANDS constant"""

    def test_read_only_commands_coverage(self):
        """Test that READ_ONLY_OC_COMMANDS covers expected read-only commands"""
        # Should include common read-only commands
        assert "oc get" in READ_ONLY_OC_COMMANDS

        # The constant should be a tuple of strings
        assert isinstance(READ_ONLY_OC_COMMANDS, tuple)
        assert all(isinstance(cmd, str) for cmd in READ_ONLY_OC_COMMANDS)

    def test_read_only_commands_investigation_distinction(self):
        """Test that remediation commands are not in read-only list"""
        # These should NOT be read-only (they're remediation commands)
        remediation_commands = [
            "oc scale",
            "oc set resources",
            "oc patch",
            "oc rollout restart",
        ]

        for cmd in remediation_commands:
            # None of the remediation command patterns should be in read-only list
            assert not any(cmd.startswith(ro_cmd) for ro_cmd in READ_ONLY_OC_COMMANDS)
