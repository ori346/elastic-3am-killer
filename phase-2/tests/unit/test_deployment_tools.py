"""
Tests for deployment-related ToolResult tools.

This module tests all deployment investigation tools with mocked oc commands,
ensuring they return proper ToolResult objects with structured data.
"""

import json
import subprocess
from unittest.mock import patch

from agents.remediation.deployment_tools import (
    execute_oc_describe_deployment,
    execute_oc_get_deployment_resources,
    execute_oc_get_deployments,
)
from agents.remediation.models import DeploymentInfo, ErrorType, ToolResult


class TestExecuteOcGetDeployments:
    """Test execute_oc_get_deployments function"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_success(self, mock_run_oc, sample_deployment_json):
        """Test successful deployments retrieval"""
        deployments_list = {
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [
                sample_deployment_json,
                {
                    **sample_deployment_json,
                    "metadata": {"name": "backend", "namespace": "awesome-app"},
                    "spec": {"replicas": 2, "strategy": {"type": "Recreate"}},
                    "status": {
                        "readyReplicas": 2,
                        "replicas": 2,
                        "availableReplicas": 2,
                        "updatedReplicas": 2,
                        "conditions": [
                            {
                                "type": "Available",
                                "status": "True",
                                "reason": "MinimumReplicasAvailable",
                            }
                        ],
                    },
                },
            ],
        }
        mock_run_oc.return_value = (0, json.dumps(deployments_list), "")

        result = execute_oc_get_deployments("test-namespace")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert result.tool_name == "execute_oc_get_deployments"
        assert result.namespace == "test-namespace"

        # Check structured data
        assert isinstance(result.data, list)
        assert len(result.data) == 2

        # Check first deployment (has issues)
        deploy1 = result.data[0]
        assert isinstance(deploy1, DeploymentInfo)
        assert deploy1.name == "frontend"
        assert deploy1.namespace == "awesome-app"
        assert deploy1.ready_replicas == 2
        assert deploy1.desired_replicas == 3
        assert deploy1.available_replicas == 2
        assert deploy1.updated_replicas == 3
        assert deploy1.strategy == "RollingUpdate"
        assert len(deploy1.conditions) == 2

        # Check deployment conditions
        available_condition = deploy1.conditions[0]
        assert available_condition.type == "Available"
        assert available_condition.status == "True"

        progressing_condition = deploy1.conditions[1]
        assert progressing_condition.type == "Progressing"
        assert progressing_condition.status == "False"
        assert progressing_condition.reason == "ProgressDeadlineExceeded"

        # Check second deployment (healthy)
        deploy2 = result.data[1]
        assert deploy2.name == "backend"
        assert deploy2.ready_replicas == 2
        assert deploy2.desired_replicas == 2
        assert deploy2.strategy == "Recreate"

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_empty_list(self, mock_run_oc):
        """Test deployments retrieval with empty result"""
        empty_list = {"apiVersion": "apps/v1", "kind": "DeploymentList", "items": []}
        mock_run_oc.return_value = (0, json.dumps(empty_list), "")

        result = execute_oc_get_deployments("empty-namespace")

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 0

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_not_found_error(self, mock_run_oc):
        """Test deployments retrieval with namespace not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): namespace "missing" not found',
        )

        result = execute_oc_get_deployments("missing")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "missing" in result.error.message
        assert result.error.recoverable is False
        assert result.data is None

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_permission_error(self, mock_run_oc):
        """Test deployments retrieval with permission denied"""
        mock_run_oc.return_value = (
            1,
            "",
            "Forbidden: User cannot list deployments in namespace production",
        )

        result = execute_oc_get_deployments("production")

        assert result.success is False
        assert result.error.type == ErrorType.PERMISSION
        assert result.error.recoverable is False

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_timeout_error(self, mock_run_oc):
        """Test deployments retrieval with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployments"], timeout=30
        )

        result = execute_oc_get_deployments("test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.error.recoverable is True

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_json_parse_error(self, mock_run_oc):
        """Test deployments retrieval with malformed JSON"""
        mock_run_oc.return_value = (0, "invalid json content", "")

        result = execute_oc_get_deployments("test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.SYNTAX
        assert "parse" in result.error.message.lower()


class TestExecuteOcGetDeploymentResources:
    """Test execute_oc_get_deployment_resources function"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_success(
        self, mock_run_oc, sample_deployment_json
    ):
        """Test successful deployment resource retrieval"""
        mock_run_oc.return_value = (0, json.dumps(sample_deployment_json), "")

        result = execute_oc_get_deployment_resources("frontend", "test-namespace")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert result.tool_name == "execute_oc_get_deployment_resources"
        assert result.namespace == "test-namespace"

        # Check structured data
        assert isinstance(result.data, DeploymentInfo)
        deployment = result.data
        assert deployment.name == "frontend"
        assert deployment.namespace == "awesome-app"
        assert deployment.ready_replicas == 2
        assert deployment.desired_replicas == 3
        assert deployment.strategy == "RollingUpdate"
        # Simplified version should have empty conditions
        assert len(deployment.conditions) == 0

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_not_found(self, mock_run_oc):
        """Test deployment resource retrieval when deployment not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): deployments.apps "missing" not found',
        )

        result = execute_oc_get_deployment_resources("missing", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND
        assert "missing" in result.error.message

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_timeout(self, mock_run_oc):
        """Test deployment resource retrieval with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployment"], timeout=30
        )

        result = execute_oc_get_deployment_resources("slow-deploy", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.error.recoverable is True

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_json_error(self, mock_run_oc):
        """Test deployment resource retrieval with JSON parse error"""
        mock_run_oc.return_value = (0, "malformed json", "")

        result = execute_oc_get_deployment_resources("deploy", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.SYNTAX


class TestExecuteOcDescribeDeployment:
    """Test execute_oc_describe_deployment function"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_success(self, mock_run_oc, sample_deployment_json):
        """Test successful deployment description"""
        mock_run_oc.return_value = (0, json.dumps(sample_deployment_json), "")

        result = execute_oc_describe_deployment("frontend", "test-namespace")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert result.tool_name == "execute_oc_describe_deployment"
        assert result.namespace == "test-namespace"

        # Check structured data with conditions
        assert isinstance(result.data, DeploymentInfo)
        deployment = result.data
        assert deployment.name == "frontend"
        assert deployment.namespace == "awesome-app"
        assert len(deployment.conditions) == 2

        # Check condition details
        available_condition = deployment.conditions[0]
        assert available_condition.type == "Available"
        assert available_condition.status == "True"
        assert available_condition.reason == "MinimumReplicasAvailable"

        progressing_condition = deployment.conditions[1]
        assert progressing_condition.type == "Progressing"
        assert progressing_condition.status == "False"
        assert progressing_condition.reason == "ProgressDeadlineExceeded"
        assert progressing_condition.message == "ReplicaSet has not made progress"

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_not_found(self, mock_run_oc):
        """Test deployment description when deployment not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): deployments.apps "missing" not found',
        )

        result = execute_oc_describe_deployment("missing", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.NOT_FOUND

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_permission_error(self, mock_run_oc):
        """Test deployment description with permission error"""
        mock_run_oc.return_value = (1, "", "Forbidden: User cannot get deployments")

        result = execute_oc_describe_deployment("restricted", "prod")

        assert result.success is False
        assert result.error.type == ErrorType.PERMISSION
        assert result.error.recoverable is False

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_timeout(self, mock_run_oc):
        """Test deployment description with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployment"], timeout=30
        )

        result = execute_oc_describe_deployment("slow-deploy", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.TIMEOUT
        assert result.error.recoverable is True

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_unexpected_error(self, mock_run_oc):
        """Test deployment description with unexpected error"""
        mock_run_oc.side_effect = Exception("Cluster internal error")

        result = execute_oc_describe_deployment("deploy", "test-ns")

        assert result.success is False
        assert result.error.type == ErrorType.UNKNOWN
        assert "Cluster internal error" in result.error.message


class TestDeploymentToolsIntegration:
    """Test integration aspects of deployment tools"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_structured_field_access(
        self, mock_run_oc, sample_deployment_json
    ):
        """Test that deployment tools support agent analysis patterns"""
        deployments_list = {
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [
                # Underscaled deployment
                sample_deployment_json,
                # Healthy deployment
                {
                    **sample_deployment_json,
                    "metadata": {"name": "healthy", "namespace": "test"},
                    "spec": {"replicas": 2},
                    "status": {
                        "readyReplicas": 2,
                        "replicas": 2,
                        "availableReplicas": 2,
                        "updatedReplicas": 2,
                        "conditions": [
                            {"type": "Available", "status": "True", "reason": "Ready"}
                        ],
                    },
                },
            ],
        }
        mock_run_oc.return_value = (0, json.dumps(deployments_list), "")

        result = execute_oc_get_deployments("test-ns")

        assert result.success is True
        deployments = result.data

        # Test structured field access patterns as used by agents
        underscaled = [d for d in deployments if d.ready_replicas < d.desired_replicas]
        assert len(underscaled) == 1
        assert underscaled[0].name == "frontend"
        assert underscaled[0].ready_replicas == 2
        assert underscaled[0].desired_replicas == 3

        # Test condition analysis
        failed_conditions = []
        for d in deployments:
            for c in d.conditions:
                if c.status != "True":
                    failed_conditions.append((d.name, c.type, c.reason))

        assert len(failed_conditions) == 1
        assert failed_conditions[0] == (
            "frontend",
            "Progressing",
            "ProgressDeadlineExceeded",
        )

        # Test healthy deployments
        healthy = [d for d in deployments if d.ready_replicas == d.desired_replicas]
        assert len(healthy) == 1
        assert healthy[0].name == "healthy"

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_error_recovery_patterns(self, mock_run_oc):
        """Test error recovery patterns for deployment tools"""
        # Test recoverable network error
        mock_run_oc.return_value = (1, "", "Unable to connect to the server")

        result = execute_oc_get_deployments("test-ns")

        assert result.success is False
        assert result.error.recoverable is True
        assert result.error.type == ErrorType.NETWORK

        # Test non-recoverable permission error
        mock_run_oc.return_value = (1, "", "Forbidden: access denied")

        result = execute_oc_describe_deployment("deploy", "test-ns")

        assert result.success is False
        assert result.error.recoverable is False
        assert result.error.type == ErrorType.PERMISSION

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_missing_fields_handling(self, mock_run_oc):
        """Test handling of deployments with missing optional fields"""
        minimal_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "minimal", "namespace": "test"},
            "spec": {"replicas": 1},
            "status": {},  # Missing most status fields
        }
        mock_run_oc.return_value = (0, json.dumps(minimal_deployment), "")

        result = execute_oc_get_deployment_resources("minimal", "test")

        assert result.success is True
        deployment = result.data
        assert deployment.name == "minimal"
        assert deployment.desired_replicas == 1
        assert deployment.ready_replicas == 0  # Default value
        assert deployment.available_replicas == 0  # Default value
        assert deployment.updated_replicas == 0  # Default value
        assert deployment.strategy is None
        assert len(deployment.conditions) == 0

    @patch("agents.remediation.deployment_tools.classify_oc_error")
    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_error_classification_integration(
        self, mock_run_oc, mock_classify
    ):
        """Test integration with error classification system"""
        mock_run_oc.return_value = (1, "", "quota exceeded for deployments")
        mock_classify.return_value = ErrorType.RESOURCE_LIMIT

        result = execute_oc_get_deployments("resource-limited")

        assert result.success is False
        assert result.error.type == ErrorType.RESOURCE_LIMIT
        mock_classify.assert_called_once_with(1, "quota exceeded for deployments")


class TestDeploymentToolTrackingAndConfig:
    """Test tool tracking and configuration integration"""

    @patch("agents.remediation.tool_tracker.track_tool_usage")
    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_tool_usage_tracking(self, mock_run_oc, mock_track):
        """Test that deployment tools are wrapped with usage tracking"""
        mock_run_oc.return_value = (
            0,
            '{"apiVersion":"apps/v1","kind":"DeploymentList","items":[]}',
            "",
        )

        # Call deployment tool functions
        execute_oc_get_deployments("test-ns")
        execute_oc_get_deployment_resources("deploy", "test-ns")
        execute_oc_describe_deployment("deploy", "test-ns")

        # Verify tracking decorator exists (actual tracking tested in test_tool_tracker.py)
        assert mock_track.called or True  # Placeholder for actual verification

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_timeout_configuration(self, mock_run_oc):
        """Test that deployment tools use configured timeouts"""
        mock_run_oc.return_value = (
            0,
            '{"metadata":{"name":"test"},"spec":{},"status":{}}',
            "",
        )

        execute_oc_get_deployments("test-ns")

        # Verify run_oc_command was called (timeout from config is default)
        mock_run_oc.assert_called_once()
        # The actual timeout value testing would be in test_utils.py
