"""
Deployment-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating and diagnosing deployment issues
in OpenShift clusters. All tools return ToolResult objects with structured data.
"""

import json
import subprocess

from llama_index.core.tools import FunctionTool

from .models import (
    ContainerResources,
    DeploymentCondition,
    DeploymentDetail,
    DeploymentListResult,
    DeploymentResources,
    DeploymentSummary,
    ErrorType,
    ToolResult,
)
from .tool_tracker import track_tool_usage
from .utils import classify_oc_error, create_error_result, run_oc_command


def _extract_strategy_details(deployment_spec: dict) -> tuple[str, str, str]:
    """Extract detailed rollout strategy configuration."""
    strategy = deployment_spec.get("strategy", {})
    strategy_type = strategy.get("type")

    rolling_update = strategy.get("rollingUpdate", {})
    max_surge = rolling_update.get("maxSurge")
    max_unavailable = rolling_update.get("maxUnavailable")

    return strategy_type, max_surge, max_unavailable


def _extract_deployment_selectors(deployment_spec: dict) -> dict:
    """Extract selector labels used for pod matching."""
    return deployment_spec.get("selector", {}).get("matchLabels", {})


@track_tool_usage
def oc_get_deployments(namespace: str) -> ToolResult:
    """
    List deployments in namespace with basic status (replica counts, strategy).

    Args:
        namespace: Target OpenShift namespace

    Returns:
        DeploymentListResult with deployment list or ToolError
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployments", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(stderr)
            recoverable = error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK]
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get deployments in namespace '{namespace}': {stderr}",
                tool_name="oc_get_deployments",
                recoverable=recoverable,
                raw_output=stderr,
                namespace=namespace,
            )

        try:
            deployments_json = json.loads(stdout)
            deployments = []

            for deployment_data in deployments_json.get("items", []):
                metadata = deployment_data.get("metadata", {})
                spec = deployment_data.get("spec", {})
                status = deployment_data.get("status", {})

                # Create streamlined DeploymentSummary with essential information only
                deployment = DeploymentSummary(
                    name=metadata["name"],
                    ready_replicas=status.get("readyReplicas", 0),
                    desired_replicas=spec.get("replicas", 0),
                    available_replicas=status.get("availableReplicas", 0),
                    updated_replicas=status.get("updatedReplicas", 0),
                )
                deployments.append(deployment)

            return DeploymentListResult(
                namespace=namespace,
                deployments=deployments,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployments JSON: {str(e)}",
                tool_name="oc_get_deployments",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message="Command timed out",
            tool_name="oc_get_deployments",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting deployments: {str(e)}",
            tool_name="oc_get_deployments",
            namespace=namespace,
        )


@track_tool_usage
def oc_get_deployment_resources(deployment_name: str, namespace: str) -> ToolResult:
    """
    Get deployment container resource limits and requests.

    Args:
        deployment_name: Deployment name
        namespace: Target namespace

    Returns:
        DeploymentResources with per-container resource data or ToolError
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get deployment '{deployment_name}': {stderr}",
                tool_name="oc_get_deployment_resources",
                recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                raw_output=stderr,
                namespace=namespace,
            )

        try:
            deployment_data = json.loads(stdout)
            metadata = deployment_data.get("metadata", {})
            spec = deployment_data.get("spec", {})
            status = deployment_data.get("status", {})

            # Extract per-container resource information from deployment spec
            pod_template = spec.get("template", {})
            pod_spec = pod_template.get("spec", {})

            containers = []
            for container_spec in pod_spec.get("containers", []):
                container_resource = ContainerResources(
                    name=container_spec["name"],
                    resources=container_spec.get("resources", {}),
                )
                containers.append(container_resource)

            return DeploymentResources(
                namespace=namespace,
                name=metadata["name"],
                ready_replicas=status.get("readyReplicas", 0),
                desired_replicas=spec.get("replicas", 0),
                containers=containers,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployment JSON: {str(e)}",
                tool_name="oc_get_deployment_resources",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for deployment '{deployment_name}'",
            tool_name="oc_get_deployment_resources",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting deployment '{deployment_name}': {str(e)}",
            tool_name="oc_get_deployment_resources",
            namespace=namespace,
        )


@track_tool_usage
def oc_describe_deployment(deployment_name: str, namespace: str) -> ToolResult:
    """
    Get comprehensive deployment information for debugging purposes.

    Args:
        deployment_name: Deployment name
        namespace: Target namespace

    Returns:
        DeploymentDetail with comprehensive deployment data for debugging or ToolError
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to describe deployment '{deployment_name}': {stderr}",
                tool_name="oc_describe_deployment",
                recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                raw_output=stderr,
                namespace=namespace,
            )

        try:
            deployment_data = json.loads(stdout)
            metadata = deployment_data.get("metadata", {})
            spec = deployment_data.get("spec", {})
            status = deployment_data.get("status", {})

            # Parse deployment conditions
            conditions = []
            for condition in status.get("conditions", []):
                deploy_condition = DeploymentCondition(
                    type=condition["type"],
                    status=condition["status"],
                    reason=condition.get("reason"),
                    message=condition.get("message"),
                )
                conditions.append(deploy_condition)

            # Extract detailed strategy information
            strategy_type, max_surge, max_unavailable = _extract_strategy_details(spec)

            # Extract selector labels
            selector_labels = _extract_deployment_selectors(spec)

            return DeploymentDetail(
                namespace=namespace,
                name=metadata["name"],
                ready_replicas=status.get("readyReplicas", 0),
                desired_replicas=spec.get("replicas", 0),
                available_replicas=status.get("availableReplicas", 0),
                updated_replicas=status.get("updatedReplicas", 0),
                unavailable_replicas=status.get("unavailableReplicas", 0),
                strategy_type=strategy_type,
                max_surge=max_surge,
                max_unavailable=max_unavailable,
                observed_generation=status.get("observedGeneration"),
                progress_deadline_seconds=spec.get("progressDeadlineSeconds"),
                labels=metadata.get("labels", {}),
                selector_labels=selector_labels,
                conditions=conditions,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployment JSON: {str(e)}",
                tool_name="oc_describe_deployment",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for deployment '{deployment_name}'",
            tool_name="oc_describe_deployment",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error describing deployment '{deployment_name}': {str(e)}",
            tool_name="oc_describe_deployment",
            namespace=namespace,
        )


# Tool definitions for LlamaIndex
deployment_tools = [
    FunctionTool.from_defaults(
        fn=oc_get_deployments,
        name="oc_get_deployments",
        description="List deployments in namespace with basic status. Args: namespace (str) - target namespace. Returns: DeploymentListResult with replica counts and strategy. Use: deployment overview and scaling status checks.",
    ),
    FunctionTool.from_defaults(
        fn=oc_get_deployment_resources,
        name="oc_get_deployment_resources",
        description="Get deployment container resource configuration. Args: deployment_name (str), namespace (str). Returns: DeploymentResources with CPU/memory limits and requests. Use: resource analysis and OOMKilled investigations.",
    ),
    FunctionTool.from_defaults(
        fn=oc_describe_deployment,
        name="oc_describe_deployment",
        description="Get comprehensive deployment debugging info. Args: deployment_name (str), namespace (str). Returns: DeploymentDetail with replica counts, strategy, rollout status, conditions. Use: deployment failures, stuck rollouts, scaling issues.",
    ),
]
