"""
Deployment-related tools for OpenShift remediation agent.

This module provides tools for investigating and diagnosing deployment issues
in OpenShift clusters.
"""

import json
import subprocess

from configs import TIMEOUTS
from llama_index.core.tools import FunctionTool

from .tool_tracker import track_tool_usage
from .utils import execute_oc_command_with_error_handling


@track_tool_usage
def execute_oc_get_deployments(namespace: str) -> str:
    """
    Execute 'oc get deployments' command for a specific namespace.
    Returns compacted output with minimal whitespace while preserving table structure.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        Compact deployment listing
    """
    return execute_oc_command_with_error_handling(
        command=["oc", "get", "deployments", "-n", namespace],
        success_message_template=f"Deployments in '{namespace}':\n{{stdout}}",
        error_message_template="Error getting deployments: {stderr}",
    )


@track_tool_usage
def execute_oc_get_deployment_resources(deployment_name: str, namespace: str) -> str:
    """
    Execute 'oc get deployment' command to retrieve ONLY the container resource limits/requests.
    This is optimized to reduce token usage by extracting only what's needed for remediation.

    Args:
        deployment_name: Name of the deployment
        namespace: The OpenShift namespace

    Returns:
        Container resource configuration (limits and requests only)
    """
    try:
        # Use jsonpath to extract ONLY the container specs (resources, image, name)
        # This dramatically reduces token usage vs full YAML
        result = subprocess.run(
            [
                "oc",
                "get",
                "deployment",
                deployment_name,
                "-n",
                namespace,
                "-o",
                'jsonpath={range .spec.template.spec.containers[*]}{"Container: "}{.name}{"\\n"}{"Image: "}{.image}{"\\n"}{"Resources:\\n"}{.resources}{"\\n---\\n"}{end}',
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUTS.oc_command_default,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                return f"Deployment '{deployment_name}' found but no container resource info available (may have no limits/requests set)"

            return (
                f"Resource configuration for deployment '{deployment_name}':\n{output}"
            )
        else:
            return f"Error getting deployment resources: {result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get deployment {deployment_name}"
    except Exception as e:
        return f"Error executing oc get deployment resources: {str(e)}"


@track_tool_usage
def execute_oc_describe_deployment(deployment_name: str, namespace: str) -> str:
    """
    Get deployment details with ONLY relevant fields (replicas, conditions, strategy).
    Optimized to minimize token usage by extracting only essential information.

    Args:
        deployment_name: Name of the deployment to describe
        namespace: The OpenShift namespace

    Returns:
        Compact deployment information with only essential fields
    """
    try:
        # Get deployment info using JSON output for compact extraction
        result = subprocess.run(
            ["oc", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=TIMEOUTS.oc_command_default,
        )

        if result.returncode != 0:
            return f"Error getting deployment: {result.stderr}"

        deploy_data = json.loads(result.stdout)

        # Build compact output
        output_lines = [f"Deployment: {deploy_data['metadata']['name']}"]

        # Replica status
        spec = deploy_data.get("spec", {})
        status = deploy_data.get("status", {})
        output_lines.append(
            f"Replicas: desired={spec.get('replicas', 0)} ready={status.get('readyReplicas', 0)} available={status.get('availableReplicas', 0)}"
        )

        # Strategy
        strategy = spec.get("strategy", {}).get("type", "Unknown")
        output_lines.append(f"Strategy: {strategy}")

        # Conditions (compact, only type and status)
        if "conditions" in status:
            output_lines.append("\nConditions:")
            for cond in status["conditions"]:
                output_lines.append(
                    f"  {cond.get('type', 'Unknown')}: {cond.get('status', 'Unknown')}"
                )

        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get deployment {deployment_name}"
    except Exception as e:
        return f"Error executing oc describe deployment: {str(e)}"


# Tool definitions for LlamaIndex
deployment_tools = [
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployment_resources,
        name="get_deployment_resources",
        description="""Get deployment resource configuration (CPU/memory limits and requests).

        Purpose: Check current resource allocations to identify if they need adjustment.

        Required Inputs:
        - deployment_name (str): Name of the deployment (e.g., "backend")
        - namespace (str): OpenShift namespace (e.g., "my-app")

        Returns: Container resource configuration showing limits and requests for CPU and memory

        Output format:
        Container: <name>
        Image: <image>
        Resources:
        <raw resource configuration JSON showing limits and requests>

        When to call: When investigating resource-related alerts (OOMKilled, CPU throttling)
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployments,
        name="execute_oc_get_deployments",
        description="""List all deployments in a namespace with their status.

        Purpose: See deployment health and replica counts.

        Required Inputs:
        - namespace (str): OpenShift namespace to query

        Returns: Compact table of deployments with NAME, READY, UP-TO-DATE, AVAILABLE, AGE

        When to call: When investigating deployment-related issues or to see overall deployment health
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_deployment,
        name="execute_oc_describe_deployment",
        description="""Get detailed deployment information including replicas, strategy, and conditions.

        Purpose: Deep dive into a specific deployment to diagnose issues.

        Required Inputs:
        - deployment_name (str): Name of the deployment
        - namespace (str): OpenShift namespace

        Returns: Compact deployment details including:
        - Replica status (desired, ready, available)
        - Update strategy
        - Conditions (Available, Progressing, etc.)

        When to call: When investigating deployment rollout issues or replica problems
        Note: Use execute_oc_get_events separately if you need event history
        """,
    ),
]
