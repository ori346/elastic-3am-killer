"""
Pod-related tools for OpenShift remediation agent.

This module provides tools for investigating and diagnosing pod issues
in OpenShift clusters.
"""

import json
import subprocess

from configs import LOG_COLLECTION, TIMEOUTS
from llama_index.core.tools import FunctionTool

from .tool_tracker import track_tool_usage
from .utils import (
    compact_output,
    execute_oc_command_with_error_handling,
    find_pod_by_name,
    parse_describe_field,
    parse_describe_section,
    run_oc_command,
)


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
    return execute_oc_command_with_error_handling(
        command=["oc", "get", "pods", "-n", namespace],
        success_message_template=f"Pods in '{namespace}':\n{{stdout}}",
        error_message_template="Error getting pods: {stderr}. Maybe the pod is not available? Consider to scale up the deployment."
    )


@track_tool_usage
def execute_oc_get_pod(pod_name: str, namespace: str) -> str:
    """
    Get pod details using 'oc get pod -o json' with ONLY relevant fields for remediation.
    Optimized to minimize token usage. Supports partial pod names (e.g., "frontend" will find "frontend-698f45c955-hbkjz").

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        Compact pod information including status, containers, resources, node, IP, QoS, and owner
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
        return f"Timeout executing oc get pod {pod_name}"
    except Exception as e:
        return f"Error executing oc get pod: {str(e)}"


def _extract_container_info(section_lines: list[str]) -> list[dict]:
    """Extract container information from Containers section of oc describe output."""
    containers = []
    i = 0

    while i < len(section_lines):
        line = section_lines[i]

        # Container name line starts with 2 spaces and ends with : (e.g., "  frontend-web:")
        if (
            line.startswith("  ")
            and not line.startswith("    ")
            and line.strip().endswith(":")
        ):
            container_name = line.strip().rstrip(":")
            port = "none"
            ready = "Unknown"
            limits_cpu = "none"
            limits_mem = "none"

            # Look ahead for properties (indented with 4 spaces)
            j = i + 1
            while j < len(section_lines):
                prop_line = section_lines[j]

                # Stop at next container (2-space indent with :)
                if prop_line.startswith("  ") and not prop_line.startswith("    "):
                    break

                # Extract port (4-space indent, not Host Port)
                if (
                    prop_line.startswith("    ")
                    and "Port:" in prop_line
                    and "Host Port:" not in prop_line
                ):
                    port = prop_line.split("Port:")[-1].strip().split("/")[0]

                # Extract ready status
                elif prop_line.startswith("    ") and "Ready:" in prop_line:
                    ready = prop_line.split("Ready:")[-1].strip()

                # Extract limits
                elif prop_line.startswith("    ") and prop_line.strip() == "Limits:":
                    # Next lines have cpu/memory (6-space indent)
                    k = j + 1
                    while k < len(section_lines) and section_lines[k].startswith(
                        "      "
                    ):
                        if "cpu:" in section_lines[k]:
                            limits_cpu = section_lines[k].split("cpu:")[-1].strip()
                        if "memory:" in section_lines[k]:
                            limits_mem = section_lines[k].split("memory:")[-1].strip()
                        k += 1

                j += 1

            containers.append(
                {
                    "name": container_name,
                    "port": port,
                    "ready": ready,
                    "limits_cpu": limits_cpu,
                    "limits_mem": limits_mem,
                }
            )

        i += 1

    return containers


def _extract_conditions(section_lines: list[str]) -> dict[str, str]:
    """Extract conditions from Conditions section of oc describe output."""
    key_conditions = {
        "PodScheduled",
        "Initialized",
        "Ready",
        "ContainersReady",
        "PodReadyToStartContainers",
    }
    conditions = {}

    for line in section_lines:
        parts = line.split()
        if len(parts) >= 2:
            cond_type = parts[0]
            if cond_type in key_conditions:
                conditions[cond_type] = parts[1]

    return conditions


def _extract_events(section_lines: list[str], count: int = LOG_COLLECTION.pod_events_tail_size) -> list[str]:
    """Extract last N events from Events section of oc describe output."""
    # Filter out header line
    event_lines = [
        line.strip()
        for line in section_lines
        if line.strip() and not line.strip().startswith("Type")
    ]

    # Get last N events
    last_events = event_lines[-count:] if len(event_lines) > count else event_lines

    # Truncate long events
    truncated = []
    for event in last_events:
        if len(event) > 100:
            event = event[:97] + "..."
        truncated.append(event)

    return truncated


@track_tool_usage
def execute_oc_describe_pod(pod_name: str, namespace: str) -> str:
    """
    Execute 'oc describe pod' and return compact output with only essential fields.
    Returns: Service Account, Status, Containers (name, port, ready, limits), Conditions, Events.

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        Compact pod description with service account, status, containers, conditions, and recent events
    """
    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return f"Error describing pod: Pod that starts with {actual_pod_name} does not exist in namespace. Maybe the pod is not available? Consider to scale up the deployment."

        # Execute oc describe pod
        returncode, stdout, stderr = run_oc_command(
            ["oc", "describe", "pod", actual_pod_name, "-n", namespace]
        )

        if returncode != 0:
            return f"Error describing pod: {stderr}"

        # Parse output
        lines = stdout.split("\n")

        # Build compact output
        output_lines = [f"Pod: {actual_pod_name}"]

        # Extract Service Account and Status
        service_account = parse_describe_field(lines, "Service Account")
        status = parse_describe_field(lines, "Status")
        output_lines.append(f"Service Account: {service_account or 'default'}")
        output_lines.append(f"Status: {status or 'Unknown'}")

        # Extract Containers
        output_lines.append("\nContainers:")
        containers_section = parse_describe_section(lines, "Containers")
        containers = _extract_container_info(containers_section)

        for container in containers:
            output_lines.append(
                f"  - {container['name']}: port={container['port']} ready={container['ready']}"
            )
            if container["limits_cpu"] != "none" or container["limits_mem"] != "none":
                output_lines.append(
                    f"    Limits: cpu={container['limits_cpu']} memory={container['limits_mem']}"
                )

        # Extract Conditions
        output_lines.append("\nConditions:")
        conditions_section = parse_describe_section(lines, "Conditions")
        conditions = _extract_conditions(conditions_section)

        for cond_type, cond_status in conditions.items():
            output_lines.append(f"  {cond_type}: {cond_status}")

        # Extract Events
        output_lines.append(f"\nEvents (last {LOG_COLLECTION.pod_events_tail_size}):")
        events_section = parse_describe_section(lines, "Events")
        events = _extract_events(events_section, count=LOG_COLLECTION.pod_events_tail_size)

        if events:
            for event in events:
                output_lines.append(f"  {event}")
        else:
            output_lines.append("  No events found")

        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc describe pod {pod_name}"
    except Exception as e:
        return f"Error executing oc describe pod: {str(e)}"


@track_tool_usage
def execute_oc_get_events(
    namespace: str, tail: int = LOG_COLLECTION.events_tail_size
) -> str:
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
        cmd = (
            f"oc get events -n {namespace} --sort-by='.lastTimestamp' | tail -n {tail}"
        )

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

        output = f"Events in '{namespace}' (last {lines_count}):\n"
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
                [
                    "oc",
                    "logs",
                    actual_pod_name,
                    "-n",
                    namespace,
                    f"--tail={LOG_COLLECTION.logs_tail_default}",
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUTS.oc_command_default,
            )
            if result.returncode == 0:
                return f"Logs for pod '{actual_pod_name}' (last {LOG_COLLECTION.logs_tail_default} lines):\n{result.stdout}"
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
        fn=execute_oc_get_pod,
        name="execute_oc_get_pod",
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
        Note: Use execute_oc_describe_pod if you need conditions and events
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_pod,
        name="execute_oc_describe_pod",
        description="""Get pod description with service account, conditions, and recent events.

        Purpose: Comprehensive pod analysis including conditions and events.

        Required Inputs:
        - pod_name (str): Name of the pod (supports partial names like "microservice-auth")
        - namespace (str): OpenShift namespace

        Returns: Compact pod description including:
        - Service Account
        - Pod status
        - Container details (name, port, ready status, resource limits)
        - Pod conditions (PodScheduled, Ready, ContainersReady, etc.)
        - Recent events (last 5 events)

        Features:
        - Supports partial pod names (e.g., "frontend" matches "frontend-698f45c955-hbkjz")
        - Automatically finds full pod name if partial match provided
        - Optimized output focusing only on essential troubleshooting fields

        When to call: When you need comprehensive pod information including conditions and recent events
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
