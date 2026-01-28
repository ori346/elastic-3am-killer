"""
Deployment-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating and diagnosing deployment issues
in OpenShift clusters. All tools return ToolResult objects with structured data.
"""

import json
import subprocess

from llama_index.core.tools import FunctionTool

from .models import DeploymentCondition, DeploymentInfo, ErrorType, ToolResult
from .tool_tracker import track_tool_usage
from .utils import classify_oc_error, create_error_result, run_oc_command


@track_tool_usage
def execute_oc_get_deployments(namespace: str) -> ToolResult:
    """
    Get all deployments in a namespace with structured output.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        ToolResult with List[DeploymentInfo] on success or ToolError on failure
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

            # Simple deployment info focused on resources
            deployment = DeploymentInfo(
                name=metadata["name"],
                namespace=metadata["namespace"],
                ready_replicas=status.get("readyReplicas", 0),
                desired_replicas=spec.get("replicas", 0),
                available_replicas=status.get("availableReplicas", 0),
                updated_replicas=status.get("updatedReplicas", 0),
                strategy=spec.get("strategy", {}).get("type"),
                conditions=[],  # Simplified - focus on resources
            )

            return ToolResult(
                success=True,
                data=deployment,
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
        description="""Get all deployments in a namespace with structured output.

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: List[DeploymentInfo] on success, None on error
        - error: ToolError with type, message, recoverable, suggestion on failure

        DeploymentInfo contains:
        - name, namespace, ready_replicas, desired_replicas, available_replicas
        - updated_replicas, strategy, conditions

        Usage:
        result = execute_oc_get_deployments("namespace")
        if result.success:
            for deployment in result.data:
                if deployment.ready_replicas < deployment.desired_replicas:
                    # Handle deployment with unready replicas
                    pass
        else:
            if result.error.recoverable:
                # Can retry this operation
                pass
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployment_resources,
        name="execute_oc_get_deployment_resources",
        description="""Get deployment resource configuration with structured output.

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: DeploymentInfo on success, None on error
        - error: ToolError on failure

        DeploymentInfo contains resource and replica information for analyzing
        deployment configuration and scaling needs.

        Usage:
        result = execute_oc_get_deployment_resources("deployment_name", "namespace")
        if result.success:
            deployment = result.data
            # Check replica status for scaling issues
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_deployment,
        name="execute_oc_describe_deployment",
        description="""Get detailed deployment information with structured output.

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: DeploymentInfo (with detailed conditions) on success, None on error
        - error: ToolError on failure

        DeploymentInfo includes deployment conditions that help diagnose:
        - Available condition: whether replicas are available
        - Progressing condition: whether rollout is progressing
        - ReplicaFailure condition: if replica creation failed

        Usage:
        result = execute_oc_describe_deployment("deployment_name", "namespace")
        if result.success:
            deployment = result.data
            failed_conditions = [c for c in deployment.conditions if c.status != "True"]
            # Analyze failed conditions for deployment issues
        """,
    ),
]
