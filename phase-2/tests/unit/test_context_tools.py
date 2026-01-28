"""
import pytest

Tests for context management ToolResult tools.

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
from agents.remediation.models import ErrorType, ToolResult


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

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert result.tool_name == "read_alert_diagnostics_data"
        assert result.namespace == "production"

        # Check structured data
        assert isinstance(result.data, dict)
        data = result.data
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

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "No alert diagnostics data found" in result.error.message
        assert "shared context" in result.error.message
        assert "namespace, alert name" in result.error.message
        assert "Workflow Coordinator" in result.error.suggestion

    @pytest.mark.asyncio
    async def test_read_alert_data_invalid_state_type(self, mock_context):
        """Test reading alert data when state is not a dict"""
        mock_context.store.get = AsyncMock(return_value="invalid_state_type")

        result = await read_alert_diagnostics_data(mock_context)

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "shared context" in result.error.message

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

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "incomplete" in result.error.message.lower()
        assert "namespace and alert name" in result.error.message
        assert "Cannot target remediation efforts" in result.error.message

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

        assert result.success is True
        data = result.data
        assert data["namespace"] == "test-ns"
        assert data["alert_name"] == "TestAlert"
        assert data["alert_diagnostics"] == ""  # Default
        assert data["alert_status"] == "unknown"  # Default
        assert data["recommendation"] == ""  # Default

    @pytest.mark.asyncio
    async def test_read_alert_data_context_exception(self, mock_context):
        """Test reading alert data with context store exception"""
        mock_context.store.get = AsyncMock(
            side_effect=Exception("Context store unavailable")
        )

        result = await read_alert_diagnostics_data(mock_context)

        assert result.success is False
        assert result.error.type == ErrorType.UNKNOWN
        assert "Failed to access shared context store" in result.error.message
        assert "Context store unavailable" in result.error.message
        assert "Cannot proceed with remediation investigation" in result.error.message
        assert "connectivity" in result.error.suggestion


class TestWriteRemediationPlan:
    """Test write_remediation_plan function"""

    @pytest.mark.asyncio
    async def test_write_plan_success(self, mock_context):
        """Test successful remediation plan writing"""
        # Mock context store edit_state - setup proper async context manager

        class MockEditState:
            async def __aenter__(self):
                return {"state": {}}

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_context.store.edit_state = lambda: MockEditState()

        explanation = "Backend deployment has insufficient CPU causing latency. Increasing limits."
        commands = [
            "oc set resources deployment backend -n production --limits=cpu=1000m,memory=512Mi",
            "oc set resources deployment backend -n production --requests=cpu=500m,memory=256Mi",
        ]

        result = await write_remediation_plan(mock_context, explanation, commands)

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert result.tool_name == "write_remediation_plan"
        assert result.namespace is None  # Context tools are not namespace-specific

        # Check structured data
        assert isinstance(result.data, dict)
        data = result.data
        assert data["plan_stored"] is True
        assert data["explanation"] == explanation
        assert data["commands_count"] == 2
        assert data["commands"] == commands
        assert (
            "Handoff to Workflow Coordinator for execution - This is MANDATORY"
            in data["next_step"]
        )

    @pytest.mark.asyncio
    async def test_write_plan_no_commands(self, mock_context):
        """Test remediation plan writing with no commands"""
        result = await write_remediation_plan(mock_context, "Some explanation", [])

        assert result.success is False
        assert result.error.type == ErrorType.SYNTAX
        assert "No remediation commands provided" in result.error.message
        assert "Alert remediation requires executable actions" in result.error.message
        assert "oc set resources" in result.error.suggestion

    @pytest.mark.asyncio
    async def test_write_plan_read_only_commands(self, mock_context):
        """Test remediation plan writing with read-only commands"""
        invalid_commands = [
            "oc get pods -n production",
            "oc describe deployment backend -n production",
            "oc logs backend-pod -n production",
        ]

        result = await write_remediation_plan(
            mock_context, "Check backend status", invalid_commands
        )

        assert result.success is False
        assert result.error.type == ErrorType.SYNTAX
        assert "Read-only commands cannot remediate alerts" in result.error.message
        assert (
            "only gather information and do not modify cluster state"
            in result.error.message
        )
        assert all(cmd in result.error.message for cmd in invalid_commands)
        assert "oc set resources" in result.error.suggestion

    @pytest.mark.asyncio
    async def test_write_plan_mixed_commands(self, mock_context):
        """Test remediation plan with mix of valid and invalid commands"""
        mixed_commands = [
            "oc set resources deployment backend -n prod --limits=cpu=1000m",
            "oc get pods -n prod",  # Read-only - invalid
            "oc scale deployment frontend -n prod --replicas=3",
        ]

        result = await write_remediation_plan(
            mock_context, "Scale and check", mixed_commands
        )

        assert result.success is False
        assert result.error.type == ErrorType.SYNTAX
        assert "oc get pods -n prod" in result.error.message
        # Should only include the invalid command, not the valid ones

    @pytest.mark.asyncio
    async def test_write_plan_context_store_error(self, mock_context):
        """Test remediation plan writing with context store error"""

        def failing_edit_state():
            raise Exception("Context store write failed")

        mock_context.store.edit_state = failing_edit_state

        commands = ["oc set resources deployment web -n app --limits=cpu=500m"]

        result = await write_remediation_plan(mock_context, "Fix CPU limits", commands)

        assert result.success is False
        assert result.error.type == ErrorType.UNKNOWN
        assert "Failed to store remediation plan" in result.error.message
        assert "Failed to store remediation plan" in result.error.message
        assert "Context store write failed" in result.error.message

    @pytest.mark.asyncio
    async def test_write_plan_command_validation_patterns(self, mock_context):
        """Test command validation against all read-only patterns"""
        # Test each read-only command pattern
        for readonly_cmd in READ_ONLY_OC_COMMANDS:
            command = f"{readonly_cmd} deployment test -n namespace"
            result = await write_remediation_plan(
                mock_context, "Test validation", [command]
            )

            assert result.success is False, f"Should reject: {command}"
            assert result.error.type == ErrorType.SYNTAX
            assert command in result.error.message

    @pytest.mark.asyncio
    async def test_write_plan_valid_state_changing_commands(self, mock_context):
        """Test remediation plan with various valid state-changing commands"""
        # Mock successful context store
        mock_context.store.edit_state = lambda: MockEditState()

        valid_commands = [
            "oc set resources deployment web -n app --limits=cpu=500m,memory=256Mi",
            "oc scale deployment backend -n app --replicas=3",
            'oc patch deployment frontend -n app -p \'{"spec":{"template":{"spec":{"restartPolicy":"Always"}}}}\'',
            "oc rollout restart deployment api -n app",
            "oc autoscale deployment worker -n app --min=2 --max=10 --cpu-percent=80",
        ]

        result = await write_remediation_plan(
            mock_context, "Comprehensive fix", valid_commands
        )

        assert result.success is True
        assert result.data["commands_count"] == 5
        assert result.data["commands"] == valid_commands


class TestReadOnlyCommandsConstants:
    """Test READ_ONLY_OC_COMMANDS constant"""

    def test_read_only_commands_completeness(self):
        """Test that READ_ONLY_OC_COMMANDS includes expected commands"""
        expected_commands = {
            "oc get",
            "oc describe",
            "oc logs",
            "oc status",
            "oc observe",
            "oc explain",
        }

        assert all(cmd in READ_ONLY_OC_COMMANDS for cmd in expected_commands)

    def test_read_only_command_validation_logic(self):
        """Test the read-only command validation logic"""
        readonly_commands = [
            "oc get pods",
            "oc describe deployment",
            "oc logs pod-name",
            "oc status",
            "oc observe pods",
            "oc explain deployment",
        ]

        state_changing_commands = [
            "oc set resources",
            "oc scale deployment",
            "oc patch pod",
            "oc rollout restart",
            "oc create deployment",
            "oc delete pod",
            "oc apply -f",
            "oc autoscale",
        ]

        # Test that read-only commands are detected
        for cmd in readonly_commands:
            is_readonly = any(
                cmd.startswith(readonly_cmd) for readonly_cmd in READ_ONLY_OC_COMMANDS
            )
            assert is_readonly, f"Should detect {cmd} as read-only"

        # Test that state-changing commands are not detected as read-only
        for cmd in state_changing_commands:
            is_readonly = any(
                cmd.startswith(readonly_cmd) for readonly_cmd in READ_ONLY_OC_COMMANDS
            )
            assert not is_readonly, f"Should not detect {cmd} as read-only"


class TestContextToolsIntegration:
    """Test integration aspects of context tools"""

    @pytest.mark.asyncio
    async def test_alert_to_remediation_workflow(self, mock_context):
        """Test complete workflow from reading alert to writing remediation"""
        # Step 1: Mock alert data in context
        mock_context.store.get = AsyncMock(
            return_value={
                "namespace": "production",
                "alert_name": "HighMemoryUsage",
                "alert_diagnostics": "Pod web-app consuming 95% memory",
                "alert_status": "firing",
                "recommendation": "Increase memory limits for web-app deployment",
            }
        )

        # Read alert diagnostics
        read_result = await read_alert_diagnostics_data(mock_context)
        assert read_result.success is True

        alert_data = read_result.data
        assert alert_data["namespace"] == "production"
        assert "web-app" in alert_data["alert_diagnostics"]

        # Step 2: Mock context store for writing plan
        mock_context.store.edit_state = lambda: MockEditState()

        # Write remediation plan based on alert data
        explanation = (
            f"Fixing high memory usage in {alert_data['namespace']} for web-app"
        )
        commands = [
            f"oc set resources deployment web-app -n {alert_data['namespace']} --limits=memory=1Gi"
        ]

        write_result = await write_remediation_plan(mock_context, explanation, commands)
        assert write_result.success is True

        plan_data = write_result.data
        assert plan_data["plan_stored"] is True
        assert alert_data["namespace"] in plan_data["explanation"]
        assert "MANDATORY" in plan_data["next_step"]

    @pytest.mark.asyncio
    async def test_context_tools_error_handling_consistency(self, mock_context):
        """Test that context tools have consistent error handling"""
        # Test both tools with context store errors
        mock_context.store.get = AsyncMock(side_effect=Exception("Connection lost"))
        mock_context.store.edit_state = AsyncMock(side_effect=Exception("Write failed"))

        read_result = await read_alert_diagnostics_data(mock_context)
        assert read_result.success is False
        assert read_result.error.type == ErrorType.UNKNOWN
        assert "Failed to access shared context store" in read_result.error.message

        write_result = await write_remediation_plan(
            mock_context, "Test", ["oc set resources deployment test --limits=cpu=500m"]
        )
        assert write_result.success is False
        assert write_result.error.type == ErrorType.UNKNOWN
        assert "Failed to store remediation plan" in write_result.error.message

        # Both should have helpful suggestions
        assert "connectivity" in read_result.error.suggestion
        assert "connectivity" in write_result.error.suggestion

    @pytest.mark.asyncio
    async def test_context_tools_namespace_handling(self, mock_context):
        """Test namespace handling in context tools"""
        # Test read with namespace
        mock_context.store.get = AsyncMock(
            return_value={
                "namespace": "specific-ns",
                "alert_name": "TestAlert",
                "alert_diagnostics": "Test diagnostics",
                "alert_status": "firing",
            }
        )

        result = await read_alert_diagnostics_data(mock_context)
        assert result.success is True
        assert result.namespace == "specific-ns"

        # Test read without namespace (unknown)
        mock_context.store.get = AsyncMock(
            return_value={"namespace": "unknown", "alert_name": "TestAlert"}
        )

        result = await read_alert_diagnostics_data(mock_context)
        assert result.success is True
        assert result.namespace is None  # Should be None for "unknown"

        # Test write (always namespace=None for context tools)
        mock_context.store.edit_state = lambda: MockEditState()

        result = await write_remediation_plan(
            mock_context, "Test", ["oc set resources deployment test --limits=cpu=500m"]
        )
        assert result.success is True
        assert result.namespace is None  # Context tools are not namespace-specific

    @pytest.mark.asyncio
    async def test_tool_result_structure_consistency(self, mock_context):
        """Test that context tools return consistent ToolResult structures"""
        # Mock successful context operations
        mock_context.store.get = AsyncMock(
            return_value={
                "namespace": "test",
                "alert_name": "TestAlert",
                "alert_diagnostics": "Test",
                "alert_status": "firing",
            }
        )

        mock_context.store.edit_state = lambda: MockEditState()

        # Test both tools return proper ToolResult structure
        read_result = await read_alert_diagnostics_data(mock_context)
        write_result = await write_remediation_plan(
            mock_context, "Test", ["oc set resources deployment test --limits=cpu=500m"]
        )

        for result in [read_result, write_result]:
            assert isinstance(result, ToolResult)
            assert isinstance(result.success, bool)
            assert result.data is not None if result.success else True
            assert result.error is None if result.success else result.error is not None
            assert isinstance(result.tool_name, str)
            assert result.namespace is None or isinstance(result.namespace, str)
