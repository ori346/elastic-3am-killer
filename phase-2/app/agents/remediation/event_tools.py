"""
Event-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating events in OpenShift clusters.
All tools return ToolResult objects with structured data.
"""

import json
import subprocess

from configs import LOG_COLLECTION
from llama_index.core.tools import FunctionTool

from .models import ErrorType, EventType, OpenShiftEvent, OpenShiftEvents, ToolResult
from .tool_tracker import track_tool_usage
from .utils import (
    classify_oc_error,
    create_error_result,
    find_pod_by_name,
    run_oc_command,
)


@track_tool_usage
def execute_oc_get_events(
    namespace: str, tail: int = LOG_COLLECTION.events_tail_size
) -> ToolResult:
    """
    Get recent namespace events (Normal/Warning types).

    Args:
        namespace: Target namespace
        tail: Event count limit (default: config value)

    Returns:
        OpenShiftEvents with event list or ToolError
    """

    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "events", "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            error_type = classify_oc_error(stderr)
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

            return OpenShiftEvents(
                namespace=namespace,
                events=limited_events,
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
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting events: {str(e)}",
            tool_name="execute_oc_get_events",
            namespace=namespace,
        )


@track_tool_usage
def execute_oc_get_deployment_events(
    deployment_name: str, namespace: str
) -> ToolResult:
    """
    Get deployment-specific events.

    Args:
        deployment_name: Deployment name
        namespace: Target namespace

    Returns:
        OpenShiftEvents filtered by deployment or ToolError
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            [
                "oc",
                "get",
                "events",
                "--field-selector",
                f"involvedObject.name={deployment_name}",
                "-n",
                namespace,
                "-o",
                "json",
            ]
        )

        if returncode != 0:
            error_type = classify_oc_error(stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get events for deployment '{deployment_name}': {stderr}",
                tool_name="execute_oc_get_deployment_events",
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
                    reason=event_data.get("reason", ""),
                    message=event_data.get("message", ""),
                    object=event_data.get("involvedObject", {}).get(
                        "name", deployment_name
                    ),
                    count=event_data.get("count", 1),
                )
                events.append(event)

            return OpenShiftEvents(
                tool_name="execute_oc_get_deployment_events",
                namespace=namespace,
                events=events,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse deployment events JSON: {str(e)}",
                tool_name="execute_oc_get_deployment_events",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for deployment '{deployment_name}' events",
            tool_name="execute_oc_get_deployment_events",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting deployment '{deployment_name}' events: {str(e)}",
            tool_name="execute_oc_get_deployment_events",
            namespace=namespace,
        )


@track_tool_usage
def execute_oc_get_pod_events(pod_name: str, namespace: str) -> ToolResult:
    """
    Get pod-specific events. Supports partial pod name matching.

    Args:
        pod_name: Pod name (partial match supported)
        namespace: Target namespace

    Returns:
        OpenShiftEvents filtered by pod or ToolError
    """
    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return create_error_result(
                error_type=ErrorType.NOT_FOUND,
                message=f"Pod '{pod_name}' not found in namespace '{namespace}': {actual_pod_name}",
                tool_name="execute_oc_get_pod_events",
                namespace=namespace,
            )

        returncode, stdout, stderr = run_oc_command(
            [
                "oc",
                "get",
                "events",
                "--field-selector",
                f"involvedObject.name={actual_pod_name}",
                "-n",
                namespace,
                "-o",
                "json",
            ]
        )

        if returncode != 0:
            error_type = classify_oc_error(stderr)
            return create_error_result(
                error_type=error_type,
                message=f"Failed to get events for pod '{actual_pod_name}': {stderr}",
                tool_name="execute_oc_get_pod_events",
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
                    reason=event_data.get("reason", ""),
                    message=event_data.get("message", ""),
                    object=event_data.get("involvedObject", {}).get(
                        "name", actual_pod_name
                    ),
                    count=event_data.get("count", 1),
                )
                events.append(event)

            return OpenShiftEvents(
                tool_name="execute_oc_get_pod_events",
                namespace=namespace,
                events=events,
            )

        except json.JSONDecodeError as e:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Failed to parse pod events JSON: {str(e)}",
                tool_name="execute_oc_get_pod_events",
                raw_output=stdout[:500],
                namespace=namespace,
            )

    except subprocess.TimeoutExpired:
        return create_error_result(
            error_type=ErrorType.TIMEOUT,
            message=f"Command timed out for pod '{pod_name}' events",
            tool_name="execute_oc_get_pod_events",
            recoverable=True,
            namespace=namespace,
        )
    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Unexpected error getting pod '{pod_name}' events: {str(e)}",
            tool_name="execute_oc_get_pod_events",
            namespace=namespace,
        )


# Tool definitions for LlamaIndex
event_tools = [
    FunctionTool.from_defaults(
        fn=execute_oc_get_events,
        name="execute_oc_get_events",
        description="""Get recent OpenShift events from a namespace.

        Args:
        - namespace (str): OpenShift namespace to query
        - tail (int, optional): Number of recent events to return (default: from config)

        Returns:
        - OpenShiftEvents: Contains list of OpenShiftEvent objects with type, reason, message, object, count

        Use for: Cluster activity analysis, warning event identification, troubleshooting context
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployment_events,
        name="execute_oc_get_deployment_events",
        description="""Get events specifically related to a deployment.

        Args:
        - deployment_name (str): Name of the deployment to filter events for
        - namespace (str): OpenShift namespace containing the deployment

        Returns:
        - OpenShiftEvents: Contains deployment-specific events (ScalingReplicaSet, FailedCreate, rollbacks)

        Use for: Deployment scaling analysis, rollout troubleshooting, replica set issues
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_pod_events,
        name="execute_oc_get_pod_events",
        description="""Get events specifically related to a pod.

        Args:
        - pod_name (str): Pod name (supports partial matching, e.g., "frontend" matches "frontend-abc123")
        - namespace (str): OpenShift namespace containing the pod

        Returns:
        - OpenShiftEvents: Contains pod-specific events (Scheduled, Failed, FailedScheduling, Pulled)

        Use for: Pod lifecycle debugging, startup failures, scheduling issues, image pull problems
        """,
    ),
]
