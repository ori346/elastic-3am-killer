"""
Pod-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating and diagnosing pod issues
in OpenShift clusters. All tools return ToolResult objects with structured data.
"""

import json
import subprocess
from typing import Optional

from configs import LOG_COLLECTION, TIMEOUTS
from llama_index.core.tools import FunctionTool

from .models import (
    ContainerDetail,
    ErrorType,
    LogEntry,
    LogResult,
    PodDetail,
    PodDetailedResult,
    PodListResult,
    PodSummary,
    ToolError,
    ToolResult,
)
from .tool_tracker import track_tool_usage
from .utils import (
    classify_oc_error,
    create_tool_error,
    extract_container_state,
    find_pod_by_name,
    format_ready_status,
    run_oc_command,
)


def _create_log_entries(
    log_lines: list[str], container_name: str = None
) -> list[LogEntry]:
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


def _handle_oc_command_error(
    returncode: int, stderr: str, tool_name: str, operation: str, namespace: str = None
) -> ToolError:
    """Handle standard OC command errors with consistent error classification."""
    error_type = classify_oc_error(stderr)
    return create_tool_error(
        error_type=error_type,
        message=f"Failed to {operation}: {stderr}",
        tool_name=tool_name,
        recoverable=error_type in [ErrorType.TIMEOUT, ErrorType.NETWORK],
        raw_output=stderr,
        namespace=namespace,
    )


def _handle_json_parse_error(
    error: Exception, tool_name: str, raw_output: str, namespace: str = None
) -> ToolError:
    """Handle JSON parsing errors."""
    return create_tool_error(
        error_type=ErrorType.SYNTAX,
        message=f"Failed to parse JSON: {str(error)}",
        tool_name=tool_name,
        raw_output=raw_output[:500],
        namespace=namespace,
    )


def _handle_timeout_error(
    tool_name: str, operation: str, namespace: str = None
) -> ToolError:
    """Handle subprocess timeout errors."""
    return create_tool_error(
        error_type=ErrorType.TIMEOUT,
        message=f"Command timed out for {operation}",
        tool_name=tool_name,
        recoverable=True,
        namespace=namespace,
    )


def _handle_generic_error(
    error: Exception, tool_name: str, operation: str, namespace: str = None
) -> ToolError:
    """Handle unexpected generic errors."""
    return create_tool_error(
        error_type=ErrorType.UNKNOWN,
        message=f"Unexpected error {operation}: {str(error)}",
        tool_name=tool_name,
        namespace=namespace,
    )


def _handle_not_found_error(
    tool_name: str, message: str, namespace: str = None
) -> ToolError:
    """Handle resource not found errors."""
    return create_tool_error(
        error_type=ErrorType.NOT_FOUND,
        message=message,
        tool_name=tool_name,
        namespace=namespace,
    )


def _get_filtered_logs(
    pod_name: str, namespace: str, container: str, pattern: str
) -> tuple[list[str], ToolResult]:
    """Get logs with pattern filtering. Returns (log_lines, error_result or None)."""
    cmd = f"oc logs {pod_name} -n {namespace} -c {container} --tail={LOG_COLLECTION.logs_tail_with_pattern} | grep -i '{pattern}' | tail -n {LOG_COLLECTION.logs_tail_final}"
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
            result.returncode,
            result.stderr,
            "oc_get_logs",
            "get filtered logs",
            namespace,
        )
        return [], error_result
    else:
        log_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return log_lines, None


def _get_unfiltered_logs(
    pod_name: str, namespace: str, container: str
) -> tuple[list[str], ToolResult]:
    """Get unfiltered logs. Returns (log_lines, error_result or None)."""
    result = subprocess.run(
        [
            "oc",
            "logs",
            pod_name,
            "-n",
            namespace,
            "-c",
            container,
            f"--tail={LOG_COLLECTION.logs_tail_default}",
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUTS.oc_command_default,
    )

    if result.returncode != 0:
        error_result = _handle_oc_command_error(
            result.returncode, result.stderr, "oc_get_logs", "get logs", namespace
        )
        return [], error_result
    else:
        log_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return log_lines, None


def _parse_container_detail_from_json(
    pod_spec: dict, pod_status: dict
) -> list[ContainerDetail]:
    """Extract detailed container information including probes, resources, and state."""
    containers = []
    container_specs = pod_spec.get("containers", [])
    container_statuses = pod_status.get("containerStatuses", [])

    # Create a mapping for easy lookup
    status_map = {status["name"]: status for status in container_statuses}

    for container_spec in container_specs:
        name = container_spec["name"]
        status = status_map.get(name, {})

        # Extract resources
        resources = container_spec.get("resources", {})

        # Extract probe configurations
        liveness_probe = container_spec.get("livenessProbe")
        readiness_probe = container_spec.get("readinessProbe")

        # Extract container state details
        container_state = status.get("state", {})
        exit_code = None
        termination_reason = None
        termination_message = None

        if "terminated" in container_state:
            terminated = container_state["terminated"]
            exit_code = terminated.get("exitCode")
            termination_reason = terminated.get("reason")
            termination_message = terminated.get("message")

        # Extract ports and environment
        ports = container_spec.get("ports", [])
        env_vars = []
        for env in container_spec.get("env", []):
            env_item = {"name": env["name"]}
            if "value" in env:
                env_item["value"] = env["value"]
            elif "valueFrom" in env:
                env_item["valueFrom"] = str(env["valueFrom"])
            env_vars.append(env_item)

        container = ContainerDetail(
            name=name,
            image=container_spec["image"],
            ready=status.get("ready", False),
            restart_count=status.get("restartCount", 0),
            state=extract_container_state(status),
            limits=resources.get("limits"),
            requests=resources.get("requests"),
            liveness_probe=liveness_probe,
            readiness_probe=readiness_probe,
            exit_code=exit_code,
            termination_reason=termination_reason,
            termination_message=termination_message,
            ports=ports,
            environment=env_vars,
        )
        containers.append(container)

    return containers


def _extract_pod_networking(pod_status: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract pod IP and host IP from status."""
    pod_ip = pod_status.get("podIP")
    host_ip = pod_status.get("hostIP")
    return pod_ip, host_ip


def _extract_security_context(pod_spec: dict) -> Optional[dict]:
    """Extract pod-level security context configuration."""
    return pod_spec.get("securityContext")


def _extract_owner_references(pod_metadata: dict) -> list[dict]:
    """Extract owner references from pod metadata."""
    owner_refs = []
    for ref in pod_metadata.get("ownerReferences", []):
        owner_refs.append(
            {
                "kind": ref.get("kind", ""),
                "name": ref.get("name", ""),
                "uid": ref.get("uid", ""),
            }
        )
    return owner_refs


@track_tool_usage
def oc_get_pods(namespace: str) -> ToolResult:
    """
    List pods in namespace with basic status (name, phase, ready count, restarts).

    Args:
        namespace: Target namespace

    Returns:
        PodsInNamespace with pod list or ToolError
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pods", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            return _handle_oc_command_error(
                returncode,
                stderr,
                "oc_get_pods",
                f"get pods in namespace '{namespace}'",
                namespace,
            )

        # Parse JSON output into structured models
        try:
            pods_json = json.loads(stdout)
            pods = []

            for pod_data in pods_json.get("items", []):
                metadata = pod_data.get("metadata", {})
                status = pod_data.get("status", {})

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

                # Create streamlined PodSummary with essential information only
                pod = PodSummary(
                    name=metadata["name"],
                    status=status.get("phase", "Unknown"),
                    ready=format_ready_status(status.get("containerStatuses", [])),
                    restarts=sum(
                        cs.get("restartCount", 0)
                        for cs in status.get("containerStatuses", [])
                    ),
                    age=age,
                )
                pods.append(pod)

            # Successful execution with structured data
            return PodListResult(
                namespace=namespace,
                pods=pods,
            )

        except json.JSONDecodeError as e:
            return _handle_json_parse_error(e, "oc_get_pods", stdout, namespace)

    except subprocess.TimeoutExpired:
        return _handle_timeout_error("oc_get_pods", "getting pods", namespace)
    except Exception as e:
        return _handle_generic_error(
            e, "oc_get_pods", "executing oc get pods", namespace
        )


@track_tool_usage
def oc_describe_pod(pod_name: str, namespace: str) -> ToolResult:
    """
    Get detailed pod information for debugging purposes. Supports partial names.

    Args:
        pod_name: Pod name (partial match supported)
        namespace: Target namespace

    Returns:
        PodDetailedResult with comprehensive pod and container information or ToolError
    """

    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return _handle_not_found_error(
                "oc_describe_pod",
                f"Pod '{pod_name}' not found in namespace '{namespace}': {actual_pod_name}",
                namespace,
            )

        # Get pod info using JSON output
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pod", actual_pod_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            return _handle_oc_command_error(
                returncode,
                stderr,
                "oc_describe_pod",
                f"get pod '{actual_pod_name}'",
                namespace,
            )

        try:
            pod_data = json.loads(stdout)
            metadata = pod_data.get("metadata", {})
            status = pod_data.get("status", {})
            spec = pod_data.get("spec", {})

            # Parse detailed container information
            containers_detail = _parse_container_detail_from_json(spec, status)

            # Extract networking information
            pod_ip, host_ip = _extract_pod_networking(status)

            # Extract security context
            security_context = _extract_security_context(spec)

            # Extract owner references
            owner_references = _extract_owner_references(metadata)

            # Create detailed PodDetail
            pod_detail = PodDetail(
                name=metadata["name"],
                status=status.get("phase", "Unknown"),
                ready=format_ready_status(status.get("containerStatuses", [])),
                restarts=sum(
                    cs.get("restartCount", 0)
                    for cs in status.get("containerStatuses", [])
                ),
                pod_ip=pod_ip,
                host_ip=host_ip,
                labels=metadata.get("labels", {}),
                annotations=metadata.get("annotations", {}),
                service_account=spec.get("serviceAccountName"),
                security_context=security_context,
                owner_references=owner_references,
            )

            return PodDetailedResult(
                namespace=namespace,
                pod=pod_detail,
                containers=containers_detail,
            )

        except json.JSONDecodeError as e:
            return _handle_json_parse_error(e, "oc_describe_pod", stdout, namespace)

    except subprocess.TimeoutExpired:
        return _handle_timeout_error("oc_describe_pod", f"pod '{pod_name}'", namespace)
    except Exception as e:
        return _handle_generic_error(
            e, "oc_describe_pod", f"getting pod '{pod_name}'", namespace
        )


@track_tool_usage
def oc_get_logs(
    pod_name: str, namespace: str, container: str = "", pattern: str = ""
) -> ToolResult:
    """
    Get pod logs with optional pattern filtering. Supports partial pod names.

    Args:
        pod_name: Pod name (partial match supported)
        namespace: Target namespace
        container: Container name (optional)
        pattern: Text pattern filter (optional)

    Returns:
        LogResult with structured log entries or ToolError
    """

    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return _handle_not_found_error(
                "oc_get_logs",
                f"Pod for logs not found: {actual_pod_name}",
                namespace,
            )

        # Get log lines using appropriate helper function
        if pattern:
            log_lines, error_result = _get_filtered_logs(
                actual_pod_name, namespace, container, pattern
            )
            if error_result:
                return error_result
            if not log_lines:
                # No matches found - return empty LogResult
                return LogResult(
                    namespace=namespace,
                    pod_name=actual_pod_name,
                    total_lines=0,
                    entries=[],
                )
        else:
            log_lines, error_result = _get_unfiltered_logs(
                actual_pod_name, namespace, container
            )
            if error_result:
                return error_result

        # Parse log lines into LogEntry objects using helper function
        log_entries = _create_log_entries(log_lines)

        # Create LogResult
        return LogResult(
            namespace=namespace,
            pod_name=actual_pod_name,
            total_lines=len(log_entries),
            entries=log_entries,
        )

    except subprocess.TimeoutExpired:
        return _handle_timeout_error(
            "oc_get_logs", f"logs for pod '{pod_name}'", namespace
        )
    except Exception as e:
        return _handle_generic_error(
            e, "oc_get_logs", f"getting logs for pod '{pod_name}'", namespace
        )


# Tool definitions for LlamaIndex
pod_tools = [
    FunctionTool.from_defaults(
        fn=oc_get_pods,
        name="oc_get_pods",
        description="List pods in namespace with basic status. Args: namespace (str) - target namespace. Returns: PodsInNamespace with pod summaries. Use: health overview and failing pod identification.",
    ),
    FunctionTool.from_defaults(
        fn=oc_describe_pod,
        name="oc_describe_pod",
        description="Get detailed pod info for debugging. Args: pod_name (str) - supports partial matching, namespace (str). Returns: PodDetailedResult with networking, security, containers, resources, probes. Use: pod failure debugging.",
    ),
    FunctionTool.from_defaults(
        fn=oc_get_logs,
        name="oc_get_logs",
        description="Get pod logs with optional filtering. Args: pod_name (str) - supports partial matching, namespace (str), container (str) - optional, pattern (str) - optional filter. Returns: LogResult with structured log entries. Use: debugging and error analysis.",
    ),
]
