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
    LogEntry,
    LogResponse,
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
    run_oc_command,
)


def _parse_pod_conditions(pod_status: dict) -> list[PodCondition]:
    """Extract pod conditions from pod status JSON."""
    conditions = []
    for condition in pod_status.get("conditions", []):
        pod_condition = PodCondition(
            type=condition["type"],
            status=condition["status"],
            reason=condition.get("reason"),
        )
        conditions.append(pod_condition)
    return conditions


def _parse_container_info_from_json(pod_spec: dict, pod_status: dict) -> list[ContainerInfo]:
    """Extract container information from pod JSON spec and status."""
    containers = []
    container_specs = pod_spec.get("containers", [])
    container_statuses = pod_status.get("containerStatuses", [])

    # Create a mapping for easy lookup
    status_map = {status["name"]: status for status in container_statuses}

    for container_spec in container_specs:
        name = container_spec["name"]
        status = status_map.get(name, {})

        # Extract resources - only create objects when there are actual values
        resources = container_spec.get("resources", {})
        limits = None
        requests = None

        if "limits" in resources:
            limits_data = {}
            if resources["limits"].get("cpu"):
                limits_data["cpu"] = resources["limits"]["cpu"]
            if resources["limits"].get("memory"):
                limits_data["memory"] = resources["limits"]["memory"]
            if limits_data:  # Only create if there are actual limits
                limits = ResourceRequirements(**limits_data)

        if "requests" in resources:
            requests_data = {}
            if resources["requests"].get("cpu"):
                requests_data["cpu"] = resources["requests"]["cpu"]
            if resources["requests"].get("memory"):
                requests_data["memory"] = resources["requests"]["memory"]
            if requests_data:  # Only create if there are actual requests
                requests = ResourceRequirements(**requests_data)

        container = ContainerInfo(
            name=name,
            image=container_spec["image"],
            ready=status.get("ready", False),
            restart_count=status.get("restartCount", 0),
            state=extract_container_state(status),
            limits=limits,
            requests=requests,
        )
        containers.append(container)

    return containers


def _create_log_entries(log_lines: list[str], container_name: str = None) -> list[LogEntry]:
    """Convert raw log lines into structured LogEntry objects."""
    entries = []
    for line in log_lines:
        if not line.strip():
            continue

        # Simple log level detection
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

        entry = LogEntry(
            level=level,
            message=line,
            container=container_name,
        )
        entries.append(entry)
    return entries


def _handle_oc_command_error(returncode: int, stderr: str, tool_name: str, operation: str, namespace: str = None) -> ToolResult:
    """Handle standard OC command errors with consistent error classification."""
    error_type = classify_oc_error(returncode, stderr)
    return create_error_result(
        error_type=error_type,
        message=f"Failed to {operation}: {stderr}",
        tool_name=tool_name,
        recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
        raw_output=stderr,
        namespace=namespace,
    )


def _handle_json_parse_error(error: Exception, tool_name: str, raw_output: str, namespace: str = None) -> ToolResult:
    """Handle JSON parsing errors."""
    return create_error_result(
        error_type=ErrorType.SYNTAX,
        message=f"Failed to parse JSON: {str(error)}",
        tool_name=tool_name,
        raw_output=raw_output[:500],
        namespace=namespace,
    )


def _handle_timeout_error(tool_name: str, operation: str, namespace: str = None) -> ToolResult:
    """Handle subprocess timeout errors."""
    return create_error_result(
        error_type=ErrorType.TIMEOUT,
        message=f"Command timed out for {operation}",
        tool_name=tool_name,
        recoverable=True,
        namespace=namespace,
    )


def _handle_generic_error(error: Exception, tool_name: str, operation: str, namespace: str = None) -> ToolResult:
    """Handle unexpected generic errors."""
    return create_error_result(
        error_type=ErrorType.UNKNOWN,
        message=f"Unexpected error {operation}: {str(error)}",
        tool_name=tool_name,
        namespace=namespace,
    )


def _handle_not_found_error(tool_name: str, message: str, namespace: str = None) -> ToolResult:
    """Handle resource not found errors."""
    return create_error_result(
        error_type=ErrorType.NOT_FOUND,
        message=message,
        tool_name=tool_name,
        namespace=namespace,
    )


def _get_filtered_logs(pod_name: str, namespace: str, pattern: str) -> tuple[list[str], ToolResult]:
    """Get logs with pattern filtering. Returns (log_lines, error_result or None)."""
    cmd = f"oc logs {pod_name} -n {namespace} --tail={LOG_COLLECTION.logs_tail_with_pattern} | grep -i '{pattern}' | tail -n {LOG_COLLECTION.logs_tail_final}"
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=TIMEOUTS.oc_command_default,
    )

    # grep returns exit code 1 if no matches found
    if result.returncode == 1 or not result.stdout.strip():
        # No matches - return empty
        return [], None
    elif result.returncode != 0:
        error_result = _handle_oc_command_error(
            result.returncode, result.stderr, "execute_oc_logs",
            "get filtered logs", namespace
        )
        return [], error_result
    else:
        log_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return log_lines, None


def _get_unfiltered_logs(pod_name: str, namespace: str) -> tuple[list[str], ToolResult]:
    """Get unfiltered logs. Returns (log_lines, error_result or None)."""
    result = subprocess.run(
        [
            "oc",
            "logs",
            pod_name,
            "-n",
            namespace,
            f"--tail={LOG_COLLECTION.logs_tail_default}",
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUTS.oc_command_default,
    )

    if result.returncode != 0:
        error_result = _handle_oc_command_error(
            result.returncode, result.stderr, "execute_oc_logs",
            "get logs", namespace
        )
        return [], error_result
    else:
        log_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return log_lines, None


@track_tool_usage
def execute_oc_get_pods(namespace: str) -> ToolResult:
    """
    Get basic pod listing information for all pods in a namespace.

    Returns lightweight pod data similar to 'oc get pods' - name, status, ready count,
    restarts, age, node. Does NOT include detailed container specs or conditions.
    Use execute_oc_get_pod for detailed information about a specific pod.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        ToolResult with List[PodInfo] containing basic pod information on success
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pods", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            return _handle_oc_command_error(
                returncode, stderr, "execute_oc_get_pods",
                f"get pods in namespace '{namespace}'", namespace
            )

        # Parse JSON output into structured models
        try:
            pods_json = json.loads(stdout)
            pods = []

            for pod_data in pods_json.get("items", []):
                metadata = pod_data.get("metadata", {})
                status = pod_data.get("status", {})
                spec = pod_data.get("spec", {})

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

                # Create lightweight PodInfo with only basic listing information
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
                    containers=[],  # Empty - use execute_oc_get_pod for detailed container info
                    conditions=[],  # Empty - use execute_oc_get_pod for detailed conditions
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
            return _handle_json_parse_error(e, "execute_oc_get_pods", stdout, namespace)

    except subprocess.TimeoutExpired:
        return _handle_timeout_error("execute_oc_get_pods", "getting pods", namespace)
    except Exception as e:
        return _handle_generic_error(e, "execute_oc_get_pods", "executing oc get pods", namespace)


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
            return _handle_not_found_error(
                "execute_oc_get_pod",
                f"Pod '{pod_name}' not found in namespace '{namespace}': {actual_pod_name}",
                namespace
            )

        # Get pod info using JSON output
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pod", actual_pod_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            return _handle_oc_command_error(
                returncode, stderr, "execute_oc_get_pod",
                f"get pod '{actual_pod_name}'", namespace
            )

        try:
            pod_data = json.loads(stdout)
            metadata = pod_data.get("metadata", {})
            status = pod_data.get("status", {})
            spec = pod_data.get("spec", {})

            # Parse containers and conditions using helper functions
            containers = _parse_container_info_from_json(spec, status)
            conditions = _parse_pod_conditions(status)

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
            return _handle_json_parse_error(e, "execute_oc_get_pod", stdout, namespace)

    except subprocess.TimeoutExpired:
        return _handle_timeout_error("execute_oc_get_pod", f"pod '{pod_name}'", namespace)
    except Exception as e:
        return _handle_generic_error(e, "execute_oc_get_pod", f"getting pod '{pod_name}'", namespace)


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
            return _handle_not_found_error(
                "execute_oc_logs",
                f"Pod for logs not found: {actual_pod_name}",
                namespace
            )

        # Get log lines using appropriate helper function
        if pattern:
            log_lines, error_result = _get_filtered_logs(actual_pod_name, namespace, pattern)
            if error_result:
                return error_result
            if not log_lines:
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
        else:
            log_lines, error_result = _get_unfiltered_logs(actual_pod_name, namespace)
            if error_result:
                return error_result

        # Parse log lines into LogEntry objects using helper function
        log_entries = _create_log_entries(log_lines)

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
        return _handle_timeout_error("execute_oc_logs", f"logs for pod '{pod_name}'", namespace)
    except Exception as e:
        return _handle_generic_error(e, "execute_oc_logs", f"getting logs for pod '{pod_name}'", namespace)


# Tool definitions for LlamaIndex
pod_tools = [
    FunctionTool.from_defaults(
        fn=execute_oc_get_pods,
        name="execute_oc_get_pods",
        description="""List all pods in a namespace with basic status information.

        Purpose: Get a lightweight overview of all pods in a namespace, similar to 'oc get pods'.

        Args:
        - namespace: OpenShift namespace to query

        Returns: ToolResult with List[PodInfo] containing basic information:
        - name, namespace, status, ready count, restarts, age, node
        - Empty containers and conditions arrays (use execute_oc_get_pod for detailed info)

        When to use:
        - Get overall pod health overview in a namespace
        - Identify which pods are failing or have issues
        - Before investigating specific pods in detail

        Note: For detailed pod information, use execute_oc_get_pod
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_pod,
        name="execute_oc_get_pod",
        description="""Get detailed pod information with containers, conditions, and resources.

        Purpose: Deep dive into a specific pod for comprehensive diagnosis.

        Args:
        - pod_name: Pod name (supports partial names like "frontend-web")
        - namespace: OpenShift namespace

        Returns: ToolResult with PodInfo containing:
        - Basic info: name, namespace, status, ready, restarts, age, node
        - containers: List[ContainerInfo] with resource limits/requests, states, restart counts
        - conditions: List[PodCondition] with detailed pod state information

        Features:
        - Supports partial pod names (e.g., "frontend" → "frontend-698f45c955-hbkjz")
        - Comprehensive container and resource analysis
        - Pod condition checking (Ready, Initialized, Scheduled, etc.)

        When to use:
        - Investigate specific pod failures or container issues
        - Analyze resource usage and limits
        - Check pod conditions and container states

        Related: Use execute_oc_get_pod_events for event history from the event_tools module
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_logs,
        name="execute_oc_logs",
        description="""Get pod logs with structured output and optional pattern filtering.

        Purpose: Retrieve and analyze application logs from pod containers.

        Args:
        - pod_name: Pod name (supports partial names like "auth-service")
        - namespace: OpenShift namespace
        - pattern: Optional text pattern to filter logs (uses grep, e.g., "ERROR", "exception")

        Returns: ToolResult with LogResponse containing:
        - pod_name, namespace, pattern_filter: Metadata about the log request
        - total_lines: Number of log lines retrieved
        - entries: List[LogEntry] with level, message, container fields

        Features:
        - Supports partial pod names (auto-matches to full name)
        - Pattern filtering for focused analysis (e.g., only ERROR logs)
        - Automatic log level detection (ERROR, WARN, INFO, DEBUG)
        - Configurable tail limits from LOG_COLLECTION settings

        When to use:
        - Investigate application errors and exceptions
        - Analyze application behavior and performance
        - Debug startup or runtime issues
        - Search for specific log patterns or messages

        Example: execute_oc_logs("api", "default", "ERROR") → Only error logs from API pod
        """,
    ),
]
