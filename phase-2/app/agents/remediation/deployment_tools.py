"""
Deployment-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating and diagnosing deployment issues
in OpenShift clusters. All tools return ToolResult objects with structured data.
"""

import json
import subprocess

from llama_index.core.tools import FunctionTool

from .models import (
    DeploymentCondition,
    DeploymentInfo,
    DeploymentResources,
    ContainerResources,
    ErrorType,
    ToolResult,
)
from .tool_tracker import track_tool_usage
from .utils import classify_oc_error, create_error_result, run_oc_command


@track_tool_usage
def execute_oc_get_deployments(namespace: str) -> ToolResult:
    """
    Get basic deployment listing information for all deployments in a namespace.

    Returns lightweight deployment data similar to 'oc get deployments' - name, replica counts,
    and strategy. Does NOT include detailed conditions.
    Use execute_oc_describe_deployment for detailed information about a specific deployment.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        ToolResult with List[DeploymentInfo] containing basic deployment information on success
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployments", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(returncode, stderr)
            recoverable = error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK]
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get deployments in namespace '{namespace}': {stderr}",
                tool_name="execute_oc_get_deployments",
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

                # Create lightweight DeploymentInfo with basic information only
                deployment = DeploymentInfo(
                    name=metadata["name"],
                    namespace=metadata["namespace"],
                    ready_replicas=status.get("readyReplicas", 0),
                    desired_replicas=spec.get("replicas", 0),
                    available_replicas=status.get("availableReplicas", 0),
                    updated_replicas=status.get("updatedReplicas", 0),
                    strategy=spec.get("strategy", {}).get("type"),
                    conditions=[],  # Empty - use execute_oc_describe_deployment for detailed conditions
                )
                deployments.append(deployment)

            return ToolResult(
                success=True,
                data=deployments,
                error=None,
                tool_name="execute_oc_get_deployments",
                namespace=namespace,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployments JSON: {str(e)}",
                tool_name="execute_oc_get_deployments",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message="Command timed out",
            tool_name="execute_oc_get_deployments",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting deployments: {str(e)}",
            tool_name="execute_oc_get_deployments",
            namespace=namespace,
        )


@track_tool_usage
def execute_oc_get_deployment_resources(
    deployment_name: str, namespace: str
) -> ToolResult:
    """
    Get deployment container resource configuration with structured output.

    Args:
        deployment_name: Name of the deployment
        namespace: The OpenShift namespace

    Returns:
        ToolResult with DeploymentInfo (focused on resource configuration) on success or ToolError on failure
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(returncode, stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get deployment '{deployment_name}': {stderr}",
                tool_name="execute_oc_get_deployment_resources",
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
                    resources=container_spec.get("resources", {})
                )
                containers.append(container_resource)

            deployment_resources = DeploymentResources(
                name=metadata["name"],
                namespace=metadata["namespace"],
                ready_replicas=status.get("readyReplicas", 0),
                desired_replicas=spec.get("replicas", 0),
                containers=containers,
            )

            return ToolResult(
                success=True,
                data=deployment_resources,
                error=None,
                tool_name="execute_oc_get_deployment_resources",
                namespace=namespace,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployment JSON: {str(e)}",
                tool_name="execute_oc_get_deployment_resources",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for deployment '{deployment_name}'",
            tool_name="execute_oc_get_deployment_resources",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting deployment '{deployment_name}': {str(e)}",
            tool_name="execute_oc_get_deployment_resources",
            namespace=namespace,
        )


@track_tool_usage
def execute_oc_describe_deployment(deployment_name: str, namespace: str) -> ToolResult:
    """
    Get detailed deployment information with structured output.

    Args:
        deployment_name: Name of the deployment to describe
        namespace: The OpenShift namespace

    Returns:
        ToolResult with DeploymentInfo (with conditions) on success or ToolError on failure
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(returncode, stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to describe deployment '{deployment_name}': {stderr}",
                tool_name="execute_oc_describe_deployment",
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

            deployment = DeploymentInfo(
                name=metadata["name"],
                namespace=metadata["namespace"],
                ready_replicas=status.get("readyReplicas", 0),
                desired_replicas=spec.get("replicas", 0),
                available_replicas=status.get("availableReplicas", 0),
                updated_replicas=status.get("updatedReplicas", 0),
                strategy=spec.get("strategy", {}).get("type"),
                conditions=conditions,
            )

            return ToolResult(
                success=True,
                data=deployment,
                error=None,
                tool_name="execute_oc_describe_deployment",
                namespace=namespace,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployment JSON: {str(e)}",
                tool_name="execute_oc_describe_deployment",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for deployment '{deployment_name}'",
            tool_name="execute_oc_describe_deployment",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error describing deployment '{deployment_name}': {str(e)}",
            tool_name="execute_oc_describe_deployment",
            namespace=namespace,
        )


# Tool definitions for LlamaIndex
deployment_tools = [
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployments,
        name="execute_oc_get_deployments",
        description="""List all deployments in a namespace with basic status information.

        Purpose: Get a lightweight overview of all deployments in a namespace, similar to 'oc get deployments'.

        Args:
        - namespace: OpenShift namespace to query

        Returns: ToolResult with List[DeploymentInfo] containing basic information:
        - name, namespace, ready_replicas, desired_replicas, available_replicas
        - updated_replicas: Number of replicas updated to latest revision
        - strategy: Deployment strategy (RollingUpdate, Recreate)
        - Empty conditions array (use execute_oc_describe_deployment for detailed conditions)

        When to use:
        - Get overview of all deployments in a namespace
        - Identify deployments with scaling issues (ready != desired replicas)
        - Quick health check of deployment replica status
        - Before investigating specific deployments in detail

        Note: For detailed deployment conditions and troubleshooting, use execute_oc_describe_deployment

        Example: If ready_replicas < desired_replicas, investigate further with execute_oc_describe_deployment
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployment_resources,
        name="execute_oc_get_deployment_resources",
        description="""Get deployment container resource configuration (CPU, memory, GPU).

        Purpose: Analyze resource limits and requests for deployment containers.

        Args:
        - deployment_name: Name of the deployment to analyze
        - namespace: OpenShift namespace

        Returns: ToolResult with DeploymentResources containing:
        - name, namespace, ready_replicas, desired_replicas
        - containers: List[ContainerResources] with per-container resource details:
          - CPU limits/requests (e.g., "500m", "2")
          - Memory limits/requests (e.g., "128Mi", "2Gi")
          - GPU limits/requests (e.g., "1", "2" from nvidia.com/gpu, amd.com/gpu)

        Features:
        - Supports all major GPU vendors (NVIDIA, AMD, Intel)
        - Shows both limits (maximum) and requests (guaranteed)
        - Per-container breakdown for multi-container deployments

        When to use:
        - Investigate resource-related alerts (OOMKilled, CPU throttling)
        - Check if containers have appropriate resource limits
        - Analyze resource allocation before scaling decisions
        - Diagnose performance issues related to resource constraints

        Example: Container with no memory limit may cause OOMKilled issues
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_deployment,
        name="execute_oc_describe_deployment",
        description="""Get detailed deployment information with conditions for troubleshooting.

        Purpose: Deep dive into a specific deployment's status and conditions.

        Args:
        - deployment_name: Name of the deployment to analyze
        - namespace: OpenShift namespace

        Returns: ToolResult with DeploymentInfo containing:
        - Basic info: name, namespace, replica counts, strategy
        - conditions: List[DeploymentCondition] with detailed status information:
          - Available: Whether replicas are available to serve requests
          - Progressing: Whether rollout is progressing successfully
          - ReplicaFailure: If replica creation has failed

        Features:
        - Detailed condition analysis for deployment troubleshooting
        - Replica count breakdown (ready, available, updated, desired)
        - Deployment strategy information (RollingUpdate vs Recreate)

        When to use:
        - Investigate specific deployment failures or stuck rollouts
        - Analyze why a deployment isn't reaching desired replica count
        - Check deployment conditions when pods aren't starting
        - Debug rollout issues and deployment strategy problems

        Example: Progressing=False may indicate resource constraints or image pull failures
        """,
    ),
]
