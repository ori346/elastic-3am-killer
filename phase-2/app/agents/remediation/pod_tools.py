"""
Pod-related tools for OpenShift remediation agent.

This module provides tools for investigating and diagnosing pod issues
in OpenShift clusters.
"""

import json
import subprocess

from llama_index.core.tools import FunctionTool

from configs import TIMEOUTS, LOG_COLLECTION
from .tool_tracker import track_tool_usage
from .utils import run_oc_command, find_pod_by_name, compact_output


@track_tool_usage
def execute_oc_get_pods(namespace: str) -> str:
    """
    Execute 'oc get pods' command for a specific namespace.
    Returns compacted output with minimal whitespace while preserving table structure.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        Compact pod listing
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pods", "-n", namespace]
        )
        if returncode == 0:
            return f"Pods in '{namespace}':\n" + compact_output(stdout)
        else:
            return f"Error getting pods: {stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get pods for namespace {namespace}"
    except Exception as e:
        return f"Error executing oc get pods: {str(e)}"


@track_tool_usage
def execute_oc_describe_pod(pod_name: str, namespace: str) -> str:
    """
    Get pod details with ONLY relevant fields for remediation (status, containers, resources).
    Optimized to minimize token usage. Supports partial pod names (e.g., "frontend" will find "frontend-698f45c955-hbkjz").

    Args:
        pod_name: Name of the pod to describe (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        Compact pod information with only essential fields
    """
    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return f"Error getting pod: {actual_pod_name}"

        # Get pod info using JSON output
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pod", actual_pod_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            return f"Error getting pod: {stderr}"

        pod_data = json.loads(stdout)

        # Build compact output
        output_lines = [f"Pod: {pod_data['metadata']['name']}"]
        output_lines.append(f"Status: {pod_data['status'].get('phase', 'Unknown')}")
        output_lines.append(
            f"ServiceAccount: {pod_data['spec'].get('serviceAccountName', 'default')}"
        )

        # Container info
        output_lines.append("\nContainers:")
        for container in pod_data["spec"].get("containers", []):
            output_lines.append(f"  - {container['name']}: {container['image']}")
            if "resources" in container:
                res = container["resources"]
                if "limits" in res:
                    output_lines.append(
                        f"    Limits: cpu={res['limits'].get('cpu', 'none')} mem={res['limits'].get('memory', 'none')}"
                    )
                if "requests" in res:
                    output_lines.append(
                        f"    Requests: cpu={res['requests'].get('cpu', 'none')} mem={res['requests'].get('memory', 'none')}"
                    )

        # Container statuses
        if "containerStatuses" in pod_data["status"]:
            output_lines.append("\nContainer Status:")
            for cs in pod_data["status"]["containerStatuses"]:
                state = (
                    list(cs.get("state", {}).keys())[0]
                    if cs.get("state")
                    else "unknown"
                )
                output_lines.append(
                    f"  - {cs['name']}: ready={cs.get('ready', False)} restarts={cs.get('restartCount', 0)} state={state}"
                )

        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc describe pod {pod_name}"
    except Exception as e:
        return f"Error executing oc describe pod: {str(e)}"


@track_tool_usage
def execute_oc_get_events(namespace: str, tail: int = LOG_COLLECTION.events_tail_size) -> str:
    """
    Execute 'oc get events' for a specific namespace.
    Returns last N events in the namespace. Output is compacted to reduce token usage.

    Args:
        namespace: The OpenShift namespace to query
        tail: Number of recent events to return (default: from config for token efficiency)

    Returns:
        Compact event listing (last N events in the namespace, sorted by timestamp)
    """
    try:
        # Get recent events from namespace and return last N events
        # This returns all recent events, not filtered by specific resource
        cmd = f"oc get events -n {namespace} --sort-by='.lastTimestamp' | tail -n {tail}"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUTS.oc_command_default,
        )

        # grep returns exit code 1 if no matches found
        if result.returncode == 1 or not result.stdout.strip():
            return f"No events found in namespace '{namespace}'"

        if result.returncode != 0:
            return f"Error getting events: {result.stderr}"

        # Remove extra whitespace and compact output
        compacted = compact_output(result.stdout)
        lines_count = len(compacted.split("\n"))

        output = (
            f"Events in '{namespace}' (last {lines_count}):\n"
        )
        output += compacted

        return output

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get events for namespace {namespace}"
    except Exception as e:
        return f"Error executing oc get events: {str(e)}"


@track_tool_usage
def execute_oc_logs(pod_name: str, namespace: str, pattern: str = "") -> str:
    """
    Execute 'oc logs' command for a specific pod.
    Returns only last N lines by default to minimize token usage.
    Supports partial pod names (e.g., "backend" will find "backend-b-698f45c955-hbkjz").

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace
        pattern: Optional text pattern to filter logs (uses grep)

    Returns:
        Command output as string (last N lines or filtered by pattern)
    """

    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return f"Error getting logs: {actual_pod_name}"

        # If pattern is provided, use grep to filter logs
        if pattern:
            cmd = f"oc logs {actual_pod_name} -n {namespace} --tail={LOG_COLLECTION.logs_tail_with_pattern} | grep -i '{pattern}' | tail -n {LOG_COLLECTION.logs_tail_final}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=TIMEOUTS.oc_command_default,
            )
            # grep returns exit code 1 if no matches found
            if result.returncode == 1 or not result.stdout.strip():
                return f"No logs matching pattern '{pattern}' found for pod '{actual_pod_name}'"
            elif result.returncode != 0:
                return f"Error getting logs: {result.stderr}"
            else:
                return f"Logs for pod '{actual_pod_name}' matching pattern '{pattern}':\n{result.stdout}"
        else:
            # No pattern, return last N lines
            result = subprocess.run(
                ["oc", "logs", actual_pod_name, "-n", namespace, f"--tail={LOG_COLLECTION.logs_tail_default}"],
                capture_output=True,
                text=True,
                timeout=TIMEOUTS.oc_command_default,
            )
            if result.returncode == 0:
                return (
                    f"Logs for pod '{actual_pod_name}' (last {LOG_COLLECTION.logs_tail_default} lines):\n{result.stdout}"
                )
            else:
                return f"Error getting logs: {result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc logs for pod {pod_name}"
    except Exception as e:
        return f"Error executing oc logs: {str(e)}"


# Tool definitions for LlamaIndex
pod_tools = [
    FunctionTool.from_defaults(
        fn=execute_oc_get_pods,
        name="execute_oc_get_pods",
        description="""List all pods in a namespace with their status.

        Purpose: See which pods are running, pending, or failed.

        Required Inputs:
        - namespace (str): OpenShift namespace to query

        Returns: Compact table of pods with NAME, READY, STATUS, RESTARTS, AGE

        When to call: When investigating pod-related issues or to see overall pod health
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_pod,
        name="execute_oc_describe_pod",
        description="""Get detailed pod information including status, containers, and resources.

        Purpose: Deep dive into a specific pod to diagnose issues.

        Required Inputs:
        - pod_name (str): Name of the pod (supports partial names like "microservice-auth")
        - namespace (str): OpenShift namespace

        Returns: Compact pod details including:
        - Pod status and phase
        - Container information with resource limits/requests
        - Container states and restart counts

        Features:
        - Supports partial pod names (e.g., "frontend" matches "frontend-698f45c955-hbkjz")
        - Automatically finds full pod name if partial match provided

        When to call: When investigating specific pod failures or container issues
        Note: Use execute_oc_get_events separately if you need event history
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_events,
        name="execute_oc_get_events",
        description="""Get recent OpenShift events from a namespace.

        Purpose: See recent cluster events that may indicate what happened in the namespace.

        Required Inputs:
        - namespace (str): OpenShift namespace to query
        - tail (int, optional): Number of recent events to return (default: 10 from config)

        Returns: Last N events in the namespace, sorted by timestamp

        Note: This returns ALL recent events in the namespace (not filtered by specific resource).
        Use this to see overall namespace activity and recent cluster events.

        When to call: When investigating issues to see recent event history and warnings
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_logs,
        name="execute_oc_logs",
        description="""Get pod logs with optional pattern filtering.

        Purpose: Read application logs to diagnose errors or issues.

        Required Inputs:
        - pod_name (str): Name of the pod (supports partial names)
        - namespace (str): OpenShift namespace
        - pattern (str, optional): Text pattern to filter logs with grep

        Returns: Last 5 lines of logs (or last 10 matching lines if pattern provided)

        Features:
        - Supports partial pod names (auto-matches to full name)
        - Optional grep pattern filtering
        - Token-optimized (returns only recent/relevant logs)

        When to call: When investigating application errors or behavior
        """,
    ),
]
