"""
Pod-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating and diagnosing pod issues
in OpenShift clusters. All tools return ToolResult objects with structured data.
"""

import json
import subprocess

from configs import LOG_COLLECTION, TIMEOUTS
from llama_index.core.tools import FunctionTool

from .models import (
    ContainerInfo,
    ErrorType,
    EventType,
    LogEntry,
    LogResponse,
    OpenShiftEvent,
    PodCondition,
    PodInfo,
    ResourceRequirements,
    ToolResult,
)
from .tool_tracker import track_tool_usage
from .utils import (
    classify_oc_error,
    create_error_result,
    extract_container_state,
    find_pod_by_name,
    format_ready_status,
    parse_describe_field,
    parse_describe_section,
    run_oc_command,
)


@track_tool_usage
def execute_oc_get_pods(namespace: str) -> ToolResult:
    """
    Get all pods in a namespace with structured output.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        ToolResult with List[PodInfo] on success or ToolError on failure
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pods", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(returncode, stderr)
            # Make timeout and network errors recoverable
            recoverable = error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK]
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get pods in namespace '{namespace}': {stderr}",
                tool_name="execute_oc_get_pods",
                recoverable=recoverable,
                raw_output=stderr,
                namespace=namespace,
            )

        # Parse JSON output into structured models
        try:
            pods_json = json.loads(stdout)
            pods = []

            for pod_data in pods_json.get("items", []):
                metadata = pod_data.get("metadata", {})
                status = pod_data.get("status", {})
                spec = pod_data.get("spec", {})

                # Parse containers
                containers = []
                for container_spec in spec.get("containers", []):
                    container_status = next(
                        (
                            cs
                            for cs in status.get("containerStatuses", [])
                            if cs.get("name") == container_spec.get("name")
                        ),
                        {},
                    )

                    # Extract resources
                    resources = container_spec.get("resources", {})
                    limits = None
                    requests = None

                    if "limits" in resources:
                        limits = ResourceRequirements(
                            cpu=resources["limits"].get("cpu"),
                            memory=resources["limits"].get("memory"),
                        )

                    if "requests" in resources:
                        requests = ResourceRequirements(
                            cpu=resources["requests"].get("cpu"),
                            memory=resources["requests"].get("memory"),
                        )

                    container = ContainerInfo(
                        name=container_spec["name"],
                        image=container_spec["image"],
                        ready=container_status.get("ready", False),
                        restart_count=container_status.get("restartCount", 0),
                        state=extract_container_state(container_status),
                        limits=limits,
                        requests=requests,
                    )
                    containers.append(container)

                # Parse conditions
                conditions = []
                for condition in status.get("conditions", []):
                    pod_condition = PodCondition(
                        type=condition["type"],
                        status=condition["status"],
                        reason=condition.get("reason"),
                    )
                    conditions.append(pod_condition)

                # Calculate basic age from creation timestamp
                creation_time = metadata.get("creationTimestamp", "")
                age = "unknown"
                if creation_time:
                    # Simple age calculation without datetime parsing
                    age = (
                        creation_time.split("T")[0]
                        if "T" in creation_time
                        else "recent"
                    )

                # Create PodInfo
                pod = PodInfo(
                    name=metadata["name"],
                    namespace=metadata["namespace"],
                    status=status.get("phase", "Unknown"),
                    ready=format_ready_status(status.get("containerStatuses", [])),
                    restarts=sum(
                        cs.get("restartCount", 0)
                        for cs in status.get("containerStatuses", [])
                    ),
                    age=age,
                    node=spec.get("nodeName"),
                    service_account=spec.get("serviceAccountName", "default"),
                    containers=containers,
                    conditions=conditions,
                )
                pods.append(pod)

            # Successful execution with structured data
            return ToolResult(
                success=True,
                data=pods,
                error=None,
                tool_name="execute_oc_get_pods",
                namespace=namespace,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse oc command output: {str(e)}",
                tool_name="execute_oc_get_pods",
                raw_output=stdout[:500],  # Truncate for debugging
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message="Command timed out",
            tool_name="execute_oc_get_pods",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error executing oc get pods: {str(e)}",
            tool_name="execute_oc_get_pods",
            namespace=namespace,
        )


@track_tool_usage
def execute_oc_get_pod(pod_name: str, namespace: str) -> ToolResult:
    """
    Get detailed pod information with structured output.
    Supports partial pod names (e.g., "frontend" will find "frontend-698f45c955-hbkjz").

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        ToolResult with PodInfo on success or ToolError on failure
    """

    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return create_error_result(
                error_type=ErrorType.NOT_FOUND,
                message=f"Pod '{pod_name}' not found in namespace '{namespace}': {actual_pod_name}",
                tool_name="execute_oc_get_pod",
                namespace=namespace,
            )

        # Get pod info using JSON output
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pod", actual_pod_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(returncode, stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get pod '{actual_pod_name}': {stderr}",
                tool_name="execute_oc_get_pod",
                recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                raw_output=stderr,
                namespace=namespace,
            )

        try:
            pod_data = json.loads(stdout)
            metadata = pod_data.get("metadata", {})
            status = pod_data.get("status", {})
            spec = pod_data.get("spec", {})

            # Parse containers with enhanced detail
            containers = []
            for container_spec in spec.get("containers", []):
                container_status = next(
                    (
                        cs
                        for cs in status.get("containerStatuses", [])
                        if cs.get("name") == container_spec.get("name")
                    ),
                    {},
                )

                # Extract resources
                resources = container_spec.get("resources", {})
                limits = None
                requests = None

                if "limits" in resources:
                    limits = ResourceRequirements(
                        cpu=resources["limits"].get("cpu"),
                        memory=resources["limits"].get("memory"),
                    )

                if "requests" in resources:
                    requests = ResourceRequirements(
                        cpu=resources["requests"].get("cpu"),
                        memory=resources["requests"].get("memory"),
                    )

                container = ContainerInfo(
                    name=container_spec["name"],
                    image=container_spec["image"],
                    ready=container_status.get("ready", False),
                    restart_count=container_status.get("restartCount", 0),
                    state=extract_container_state(container_status),
                    limits=limits,
                    requests=requests,
                )
                containers.append(container)

            # Parse conditions
            conditions = []
            for condition in status.get("conditions", []):
                pod_condition = PodCondition(
                    type=condition["type"],
                    status=condition["status"],
                    reason=condition.get("reason"),
                )
                conditions.append(pod_condition)

            # Calculate age
            creation_time = metadata.get("creationTimestamp", "")
            age = "unknown"
            if creation_time:
                age = creation_time.split("T")[0] if "T" in creation_time else "recent"

            # Create PodInfo
            pod = PodInfo(
                name=metadata["name"],
                namespace=metadata["namespace"],
                status=status.get("phase", "Unknown"),
                ready=format_ready_status(status.get("containerStatuses", [])),
                restarts=sum(
                    cs.get("restartCount", 0)
                    for cs in status.get("containerStatuses", [])
                ),
                age=age,
                node=spec.get("nodeName"),
                service_account=spec.get("serviceAccountName", "default"),
                containers=containers,
                conditions=conditions,
            )

            return ToolResult(
                success=True,
                data=pod,
                error=None,
                tool_name="execute_oc_get_pod",
                namespace=namespace,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse pod JSON: {str(e)}",
                tool_name="execute_oc_get_pod",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for pod '{pod_name}'",
            tool_name="execute_oc_get_pod",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting pod '{pod_name}': {str(e)}",
            tool_name="execute_oc_get_pod",
            namespace=namespace,
        )


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


def _extract_events(
    section_lines: list[str], count: int = LOG_COLLECTION.pod_events_tail_size
) -> list[str]:
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
def execute_oc_describe_pod(pod_name: str, namespace: str) -> ToolResult:
    """
    Get detailed pod information with structured output including conditions and events.

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        ToolResult with PodInfo containing enhanced details from describe output
    """
    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return create_error_result(
                error_type=ErrorType.NOT_FOUND,
                message=f"Pod '{pod_name}' not found in namespace '{namespace}': {actual_pod_name}",
                tool_name="execute_oc_describe_pod",
                namespace=namespace,
            )

        # Execute oc describe pod
        returncode, stdout, stderr = run_oc_command(
            ["oc", "describe", "pod", actual_pod_name, "-n", namespace]
        )

        if returncode != 0:
            error_type = classify_oc_error(returncode, stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to describe pod '{actual_pod_name}': {stderr}",
                tool_name="execute_oc_describe_pod",
                recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                raw_output=stderr,
                namespace=namespace,
            )

        # Parse output
        lines = stdout.split("\n")

        # Extract Service Account and Status
        service_account = parse_describe_field(lines, "Service Account")
        pod_status = parse_describe_field(lines, "Status")

        # Extract and convert containers
        containers_section = parse_describe_section(lines, "Containers")
        container_dicts = _extract_container_info(containers_section)
        containers = []

        for container_dict in container_dicts:
            # Convert container dict to ContainerInfo model
            limits = None
            if (
                container_dict["limits_cpu"] != "none"
                or container_dict["limits_mem"] != "none"
            ):
                limits = ResourceRequirements(
                    cpu=(
                        container_dict["limits_cpu"]
                        if container_dict["limits_cpu"] != "none"
                        else None
                    ),
                    memory=(
                        container_dict["limits_mem"]
                        if container_dict["limits_mem"] != "none"
                        else None
                    ),
                )

            # Convert ready status string to boolean
            ready_status = container_dict["ready"]
            is_ready = ready_status.lower() in ["true", "1", "yes"]

            container = ContainerInfo(
                name=container_dict["name"],
                image="unknown",  # describe output doesn't have image info easily accessible
                ready=is_ready,
                restart_count=0,  # describe output doesn't have restart count
                state="unknown",  # describe output doesn't have simple state
                limits=limits,
                requests=None,  # describe output doesn't have requests info easily accessible
            )
            containers.append(container)

        # Extract and convert conditions
        conditions_section = parse_describe_section(lines, "Conditions")
        condition_dict = _extract_conditions(conditions_section)
        conditions = []

        for cond_type, cond_status in condition_dict.items():
            condition = PodCondition(
                type=cond_type,
                status=cond_status,
                reason=None,  # describe parsing doesn't extract reason
            )
            conditions.append(condition)

        # Calculate age and ready status - basic info since describe doesn't have creation time easily
        creation_time = parse_describe_field(lines, "Start Time")
        age = "unknown"
        if creation_time:
            age = creation_time.split("T")[0] if "T" in creation_time else "recent"

        # Calculate ready status from containers
        ready_containers = sum(1 for c in containers if c.ready)
        total_containers = len(containers)
        ready_status = f"{ready_containers}/{total_containers}" if containers else "0/0"

        # Calculate total restarts (not available in describe, use 0)
        total_restarts = sum(c.restart_count for c in containers)

        # Extract node info
        node = parse_describe_field(lines, "Node")

        # Create PodInfo
        pod_info = PodInfo(
            name=actual_pod_name,
            namespace=namespace,
            status=pod_status or "Unknown",
            ready=ready_status,
            restarts=total_restarts,
            age=age,
            node=node,
            service_account=service_account or "default",
            containers=containers,
            conditions=conditions,
        )

        return ToolResult(
            success=True,
            data=pod_info,
            error=None,
            tool_name="execute_oc_describe_pod",
            namespace=namespace,
        )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for pod '{pod_name}'",
            tool_name="execute_oc_describe_pod",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error describing pod '{pod_name}': {str(e)}",
            tool_name="execute_oc_describe_pod",
            namespace=namespace,
        )


@track_tool_usage
def execute_oc_get_events(
    namespace: str, tail: int = LOG_COLLECTION.events_tail_size
) -> ToolResult:
    """
    Get recent events from a namespace with structured output.

    Args:
        namespace: The OpenShift namespace to query
        tail: Number of recent events to return (default: from config)

    Returns:
        ToolResult with List[OpenShiftEvent] on success or ToolError on failure
    """

    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "events", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            # Check for no events found vs actual error
            if "no resources found" in stderr.lower():
                # No events is not an error, return empty list
                return ToolResult(
                    success=True,
                    data=[],
                    error=None,
                    tool_name="execute_oc_get_events",
                    namespace=namespace,
                )
            else:
                error_type = classify_oc_error(returncode, stderr)
                return create_error_result(
                    error_type=error_type,
                    message=f"Failed to get events in namespace '{namespace}': {stderr}",
                    tool_name="execute_oc_get_events",
                    recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                    raw_output=stderr,
                    namespace=namespace,
                )

        try:
            events_json = json.loads(stdout)
            events = []

            for event_data in events_json.get("items", []):
                event = OpenShiftEvent(
                    type=(
                        EventType.WARNING
                        if event_data.get("type") == "Warning"
                        else EventType.NORMAL
                    ),
                    reason=event_data.get("reason", "Unknown"),
                    message=event_data.get("message", ""),
                    object=event_data.get("involvedObject", {}).get("name", "Unknown"),
                    count=event_data.get("count", 1),
                )
                events.append(event)

            # Take last N events (prioritize warnings)
            events.sort(key=lambda e: (e.type == EventType.NORMAL, e.reason))
            limited_events = events[-tail:] if len(events) > tail else events

            return ToolResult(
                success=True,
                data=limited_events,
                error=None,
                tool_name="execute_oc_get_events",
                namespace=namespace,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse events JSON: {str(e)}",
                tool_name="execute_oc_get_events",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for namespace '{namespace}'",
            tool_name="execute_oc_get_events",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return f"Error executing oc get events: {str(e)}"


@track_tool_usage
def execute_oc_logs(pod_name: str, namespace: str, pattern: str = "") -> ToolResult:
    """
    Get pod logs with optional pattern filtering and structured output.

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace
        pattern: Optional text pattern to filter logs (uses grep)

    Returns:
        ToolResult with LogResponse containing structured log entries
    """

    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return create_error_result(
                error_type=ErrorType.NOT_FOUND,
                message=f"Pod for logs not found: {actual_pod_name}",
                tool_name="execute_oc_logs",
                namespace=namespace,
            )

        # Execute oc logs command
        if pattern:
            # Use grep to filter logs with pattern
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
                # No matches found - return empty LogResponse
                log_response = LogResponse(
                    pod_name=actual_pod_name,
                    namespace=namespace,
                    pattern_filter=pattern,
                    total_lines=0,
                    entries=[],
                )
                return ToolResult(
                    success=True,
                    data=log_response,
                    error=None,
                    tool_name="execute_oc_logs",
                    namespace=namespace,
                )
            elif result.returncode != 0:
                error_type = classify_oc_error(result.returncode, result.stderr)
                return create_error_result(
                    error_type=error_type,
                    message=f"Error getting filtered logs: {result.stderr}",
                    tool_name="execute_oc_logs",
                    recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                    raw_output=result.stderr,
                    namespace=namespace,
                )
            else:
                log_lines = (
                    result.stdout.strip().split("\n") if result.stdout.strip() else []
                )
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
            if result.returncode != 0:
                error_type = classify_oc_error(result.returncode, result.stderr)
                return create_error_result(
                    error_type=error_type,
                    message=f"Error getting logs: {result.stderr}",
                    tool_name="execute_oc_logs",
                    recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
                    raw_output=result.stderr,
                    namespace=namespace,
                )
            else:
                log_lines = (
                    result.stdout.strip().split("\n") if result.stdout.strip() else []
                )

        # Parse log lines into LogEntry objects
        log_entries = []
        for line in log_lines:
            if not line.strip():
                continue

            # Basic log level detection
            level = None
            line_upper = line.upper()
            if "ERROR" in line_upper or "FATAL" in line_upper:
                level = "ERROR"
            elif "WARN" in line_upper:
                level = "WARN"
            elif "INFO" in line_upper:
                level = "INFO"
            elif "DEBUG" in line_upper:
                level = "DEBUG"

            log_entry = LogEntry(
                level=level,
                message=line,
                container=None,  # Container info not easily available in single-container logs
            )
            log_entries.append(log_entry)

        # Create LogResponse
        log_response = LogResponse(
            pod_name=actual_pod_name,
            namespace=namespace,
            pattern_filter=pattern if pattern else None,
            total_lines=len(log_entries),
            entries=log_entries,
        )

        return ToolResult(
            success=True,
            data=log_response,
            error=None,
            tool_name="execute_oc_logs",
            namespace=namespace,
        )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Logs command timed out for pod '{pod_name}'",
            tool_name="execute_oc_logs",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Error getting logs for pod '{pod_name}': {str(e)}",
            tool_name="execute_oc_logs",
            namespace=namespace,
        )


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
        description="""Get comprehensive pod information with structured output.

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: PodInfo with enhanced details on success, None on error
        - error: ToolError with type, message, recoverable, suggestion on failure

        PodInfo contains:
        - Basic info: name, namespace, status, ready, restarts, age, node, service_account
        - containers: List[ContainerInfo] with resources, ready status, restart counts
        - conditions: List[PodCondition] with detailed pod state information

        Usage:
        result = execute_oc_describe_pod("pod-name", "namespace")
        if result.success:
            pod = result.data
            failed_conditions = [c for c in pod.conditions if c.status != "True"]
            unready_containers = [c for c in pod.containers if not c.ready]
        else:
            if result.error.recoverable:
                # Can retry this operation
                pass

        Features:
        - Supports partial pod names (e.g., "frontend" matches "frontend-698f45c955-hbkjz")
        - Structured data access for efficient agent reasoning
        - Comprehensive error handling with recovery guidance

        When to call: When you need comprehensive pod information including conditions and events
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
        description="""Get pod logs with structured output and optional filtering.

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: LogResponse with structured log entries on success, None on error
        - error: ToolError with type, message, recoverable, suggestion on failure

        LogResponse contains:
        - pod_name, namespace, container, pattern_filter metadata
        - total_lines: Total number of log lines retrieved
        - entries: List[LogEntry] with level, message, container

        Usage:
        result = execute_oc_logs("pod-name", "namespace", "ERROR")
        if result.success:
            logs = result.data
            error_entries = [entry for entry in logs.entries if entry.level == "ERROR"]
            total_errors = len(error_entries)
            for entry in logs.entries:
                print(f"{entry.level}: {entry.message}")
        else:
            if result.error.recoverable:
                # Can retry this operation
                pass

        Features:
        - Supports partial pod names (auto-matches to full name)
        - Optional grep pattern filtering
        - Basic log level detection (ERROR, WARN, INFO, DEBUG)
        - Structured data access for efficient agent reasoning

        When to call: When investigating application errors or behavior
        """,
    ),
]
