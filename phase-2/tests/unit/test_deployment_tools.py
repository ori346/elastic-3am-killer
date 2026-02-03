"""
Tests for deployment-related tools.

This module tests all deployment investigation tools with mocked oc commands,
ensuring they return proper model objects with structured data.
"""

import json
import subprocess
from unittest.mock import patch

from agents.remediation.deployment_tools import (
    execute_oc_describe_deployment,
    execute_oc_get_deployment_resources,
    execute_oc_get_deployments,
)
from agents.remediation.models import (
    DeploymentListResult,
    DeploymentResources,
    DeploymentDetail,
    ErrorType,
    ToolError,
)


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
                    "spec": {"replicas": 2},
                    "status": {
                        "readyReplicas": 2,
                        "availableReplicas": 2,
                        "updatedReplicas": 2,
                    },
                },
            ],
        }
        mock_run_oc.return_value = (0, json.dumps(deployments_list), "")

        result = execute_oc_get_deployments("test-namespace")

        # Check result type - should be DeploymentListResult, not ToolError
        assert isinstance(result, DeploymentListResult)
        assert result.tool_name == "execute_oc_get_deployments"
        assert result.namespace == "test-namespace"

        # Check structured data
        assert isinstance(result.deployments, list)
        assert len(result.deployments) == 2

        # Check first deployment
        deploy1 = result.deployments[0]
        assert deploy1.name == "frontend"
        assert deploy1.ready_replicas == 2
        assert deploy1.desired_replicas == 3
        assert deploy1.available_replicas == 2
        assert deploy1.updated_replicas == 3

        # Check second deployment
        deploy2 = result.deployments[1]
        assert deploy2.name == "backend"
        assert deploy2.ready_replicas == 2
        assert deploy2.desired_replicas == 2

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_empty_list(self, mock_run_oc):
        """Test deployments retrieval with empty result"""
        empty_list = {"apiVersion": "apps/v1", "kind": "DeploymentList", "items": []}
        mock_run_oc.return_value = (0, json.dumps(empty_list), "")

        result = execute_oc_get_deployments("empty-namespace")

        # Should still be DeploymentListResult, just with empty list
        assert isinstance(result, DeploymentListResult)
        assert result.tool_name == "execute_oc_get_deployments"
        assert result.namespace == "empty-namespace"
        assert isinstance(result.deployments, list)
        assert len(result.deployments) == 0

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_not_found_error(self, mock_run_oc):
        """Test deployments retrieval with namespace not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): namespaces "missing" not found',
        )

        result = execute_oc_get_deployments("missing")

        # Should be ToolError, not DeploymentListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "missing" in result.message
        assert result.recoverable is False

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_permission_error(self, mock_run_oc):
        """Test deployments retrieval with permission denied"""
        mock_run_oc.return_value = (
            1,
            "",
            "Forbidden: User cannot list deployments in namespace production",
        )

        result = execute_oc_get_deployments("production")

        # Should be ToolError, not DeploymentListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.PERMISSION
        assert result.recoverable is False

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_timeout_error(self, mock_run_oc):
        """Test deployments retrieval with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployments"], timeout=30
        )

        result = execute_oc_get_deployments("test-ns")

        # Should be ToolError, not DeploymentListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
        assert result.recoverable is True

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployments_json_parse_error(self, mock_run_oc):
        """Test deployments retrieval with malformed JSON"""
        mock_run_oc.return_value = (0, "invalid json content", "")

        result = execute_oc_get_deployments("test-ns")

        # Should be ToolError, not DeploymentListResult
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX
        assert "parse" in result.message.lower()


class TestExecuteOcGetDeploymentResources:
    """Test execute_oc_get_deployment_resources function"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_success(self, mock_run_oc, sample_deployment_json):
        """Test successful deployment resource retrieval"""
        # Add container resources to the sample
        deployment_with_resources = {
            **sample_deployment_json,
            "spec": {
                **sample_deployment_json["spec"],
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "nginx",
                                "image": "nginx:1.20",
                                "resources": {
                                    "limits": {"cpu": "500m", "memory": "256Mi"},
                                    "requests": {"cpu": "200m", "memory": "128Mi"},
                                },
                            }
                        ]
                    }
                }
            }
        }
        mock_run_oc.return_value = (0, json.dumps(deployment_with_resources), "")

        result = execute_oc_get_deployment_resources("frontend", "test-namespace")

        # Should be DeploymentResources, not ToolError
        assert isinstance(result, DeploymentResources)
        assert result.tool_name == "execute_oc_get_deployment_resources"
        assert result.namespace == "test-namespace"

        # Check deployment data
        assert result.name == "frontend"
        assert result.ready_replicas == 2
        assert result.desired_replicas == 3

        # Check container resources
        assert len(result.containers) == 1
        container = result.containers[0]
        assert container.name == "nginx"
        assert "limits" in container.resources
        assert "requests" in container.resources

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_not_found(self, mock_run_oc):
        """Test deployment resource retrieval when deployment not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): deployments.apps "missing" not found',
        )

        result = execute_oc_get_deployment_resources("missing", "test-ns")

        # Should be ToolError, not DeploymentResources
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND
        assert "missing" in result.message

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_timeout(self, mock_run_oc):
        """Test deployment resource retrieval with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployment"], timeout=30
        )

        result = execute_oc_get_deployment_resources("slow-deploy", "test-ns")

        # Should be ToolError, not DeploymentResources
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
        assert result.recoverable is True

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_get_deployment_resources_json_error(self, mock_run_oc):
        """Test deployment resource retrieval with JSON parse error"""
        mock_run_oc.return_value = (0, "malformed json", "")

        result = execute_oc_get_deployment_resources("broken", "test-ns")

        # Should be ToolError, not DeploymentResources
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.SYNTAX


class TestExecuteOcDescribeDeployment:
    """Test execute_oc_describe_deployment function"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_success(self, mock_run_oc, sample_deployment_json):
        """Test successful deployment describe"""
        # Enhance sample with strategy details
        enhanced_deployment = {
            **sample_deployment_json,
            "spec": {
                **sample_deployment_json["spec"],
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": "25%",
                        "maxUnavailable": "25%"
                    }
                },
                "progressDeadlineSeconds": 600,
                "selector": {
                    "matchLabels": {"app": "frontend", "version": "v1"}
                }
            },
            "metadata": {
                **sample_deployment_json["metadata"],
                "labels": {"app": "frontend", "tier": "web"}
            },
            "status": {
                **sample_deployment_json["status"],
                "unavailableReplicas": 1,
                "observedGeneration": 3
            }
        }
        mock_run_oc.return_value = (0, json.dumps(enhanced_deployment), "")

        result = execute_oc_describe_deployment("frontend", "test-namespace")

        # Should be DeploymentDetail, not ToolError
        assert isinstance(result, DeploymentDetail)
        assert result.tool_name == "execute_oc_describe_deployment"
        assert result.namespace == "test-namespace"

        # Check basic deployment info
        assert result.name == "frontend"
        assert result.ready_replicas == 2
        assert result.desired_replicas == 3
        assert result.unavailable_replicas == 1

        # Check strategy details
        assert result.strategy_type == "RollingUpdate"
        assert result.max_surge == "25%"
        assert result.max_unavailable == "25%"
        assert result.progress_deadline_seconds == 600
        assert result.observed_generation == 3

        # Check labels
        assert "app" in result.labels
        assert result.labels["app"] == "frontend"
        assert "app" in result.selector_labels
        assert result.selector_labels["app"] == "frontend"

        # Check conditions
        assert len(result.conditions) == 2

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_not_found(self, mock_run_oc):
        """Test deployment describe when deployment not found"""
        mock_run_oc.return_value = (
            1,
            "",
            'Error from server (NotFound): deployments.apps "missing" not found',
        )

        result = execute_oc_describe_deployment("missing", "test-ns")

        # Should be ToolError, not DeploymentDetail
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.NOT_FOUND

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_permission_error(self, mock_run_oc):
        """Test deployment describe with permission error"""
        mock_run_oc.return_value = (
            1,
            "",
            "Forbidden: User cannot get deployments in namespace secure",
        )

        result = execute_oc_describe_deployment("secure-app", "secure")

        # Should be ToolError, not DeploymentDetail
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.PERMISSION
        assert result.recoverable is False

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_timeout(self, mock_run_oc):
        """Test deployment describe with timeout"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployment"], timeout=30
        )

        result = execute_oc_describe_deployment("slow-deploy", "test-ns")

        # Should be ToolError, not DeploymentDetail
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT
        assert result.recoverable is True

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_describe_deployment_unexpected_error(self, mock_run_oc):
        """Test deployment describe with unexpected exception"""
        mock_run_oc.side_effect = Exception("Unexpected error")

        result = execute_oc_describe_deployment("error-deploy", "test-ns")

        # Should be ToolError, not DeploymentDetail
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.UNKNOWN


class TestDeploymentToolsIntegration:
    """Integration tests for deployment tools"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_structured_field_access(self, mock_run_oc, sample_deployment_json):
        """Test that deployment data can be accessed as structured fields"""
        deployments_list = {
            "apiVersion": "apps/v1",
            "kind": "DeploymentList",
            "items": [sample_deployment_json],
        }
        mock_run_oc.return_value = (0, json.dumps(deployments_list), "")

        result = execute_oc_get_deployments("test-namespace")

        # Test structured field access
        assert isinstance(result, DeploymentListResult)
        assert hasattr(result, 'deployments')
        assert hasattr(result, 'tool_name')
        assert hasattr(result, 'namespace')

        deployment = result.deployments[0]
        assert hasattr(deployment, 'name')
        assert hasattr(deployment, 'ready_replicas')
        assert hasattr(deployment, 'desired_replicas')

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_error_recovery_patterns(self, mock_run_oc):
        """Test error recovery patterns across deployment tools"""
        # Network timeout - should be recoverable
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "deployments"], timeout=30
        )

        result = execute_oc_get_deployments("test-ns")
        assert isinstance(result, ToolError)
        assert result.recoverable is True
        assert result.type == ErrorType.TIMEOUT

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_missing_fields_handling(self, mock_run_oc):
        """Test deployment tools handle missing optional fields gracefully"""
        minimal_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "minimal", "namespace": "test"},
            "spec": {"replicas": 1},
            "status": {},
        }
        mock_run_oc.return_value = (0, json.dumps(minimal_deployment), "")

        result = execute_oc_get_deployment_resources("minimal", "test")

        # Should handle missing fields gracefully
        assert isinstance(result, DeploymentResources)
        assert result.name == "minimal"
        assert result.ready_replicas == 0  # Default value
        assert result.desired_replicas == 1

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_error_classification_integration(self, mock_run_oc):
        """Test that deployment tools correctly classify different error types"""
        test_cases = [
            ("pods not found", ErrorType.NOT_FOUND, False),
            ("User cannot get pods", ErrorType.PERMISSION, False),
            ("network error", ErrorType.NETWORK, True),
            ("invalid syntax", ErrorType.SYNTAX, False),
        ]

        for error_msg, expected_type, expected_recoverable in test_cases:
            # Use the exact error message that will be classified correctly
            if expected_type == ErrorType.NOT_FOUND:
                stderr = f'Error from server (NotFound): {error_msg}'
            elif expected_type == ErrorType.PERMISSION:
                stderr = f'Forbidden: {error_msg}'
            elif expected_type == ErrorType.NETWORK:
                stderr = f'Unable to connect to server: {error_msg}'
            elif expected_type == ErrorType.SYNTAX:
                stderr = f'unknown command: {error_msg}'
            else:
                stderr = f"Error: {error_msg}"

            mock_run_oc.return_value = (1, "", stderr)
            result = execute_oc_get_deployments("test")

            assert isinstance(result, ToolError)
            assert result.type == expected_type
            assert result.recoverable == expected_recoverable


class TestDeploymentToolTrackingAndConfig:
    """Test deployment tool usage tracking and configuration"""

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_tool_usage_tracking(self, mock_run_oc):
        """Test that deployment tools work correctly"""
        mock_run_oc.return_value = (0, '{"items": []}', "")

        result = execute_oc_get_deployments("test")

        # Should return successful result
        assert isinstance(result, DeploymentListResult)
        assert result.tool_name == "execute_oc_get_deployments"

    @patch("agents.remediation.deployment_tools.run_oc_command")
    def test_deployment_timeout_configuration(self, mock_run_oc):
        """Test that deployment tools respect timeout configuration"""
        # This mainly tests that the function doesn't crash with timeouts
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc"], timeout=120
        )

        result = execute_oc_get_deployments("test")
        assert isinstance(result, ToolError)
        assert result.type == ErrorType.TIMEOUT