"""
Event-related tools for OpenShift Alert Remediation Specialist.

This module provides tools for investigating events in OpenShift clusters.
All tools return ToolResult objects with structured data.
"""

import json
import subprocess

from configs import LOG_COLLECTION
from llama_index.core.tools import FunctionTool

from .models import ErrorType, EventType, OpenShiftEvent, ToolResult
from .tool_tracker import track_tool_usage
from .utils import classify_oc_error, create_error_result, find_pod_by_name, run_oc_command


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
def execute_oc_get_deployment_events(
    deployment_name: str, namespace: str
) -> ToolResult:
    """
    Get events specifically related to a deployment with structured output.

    Args:
        deployment_name: Name of the deployment
        namespace: The OpenShift namespace

    Returns:
        ToolResult with List[OpenShiftEvent] for the deployment on success or ToolError on failure
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
            # Check for no events found vs actual error
            if "no resources found" in stderr.lower():
                # No events is not an error, return empty list
                return ToolResult(
                    success=True,
                    data=[],
                    error=None,
                    tool_name="execute_oc_get_deployment_events",
                    namespace=namespace,
                )
            else:
                error_type = classify_oc_error(returncode, stderr)
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

            return ToolResult(
                success=True,
                data=events,
                error=None,
                tool_name="execute_oc_get_deployment_events",
                namespace=namespace,
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
    Get events specifically related to a pod with structured output.

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        ToolResult with List[OpenShiftEvent] for the pod on success or ToolError on failure
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

        returncode, stdout, stderr = run_oc_command([
            "oc",
            "get",
            "events",
            "--field-selector",
            f"involvedObject.name={actual_pod_name}",
            "-n",
            namespace,
            "-o",
            "json"
        ])

        if returncode != 0:
            # Check for no events found vs actual error
            if "no resources found" in stderr.lower():
                # No events is not an error, return empty list
                return ToolResult(
                    success=True,
                    data=[],
                    error=None,
                    tool_name="execute_oc_get_pod_events",
                    namespace=namespace,
                )
            else:
                error_type = classify_oc_error(returncode, stderr)
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

            return ToolResult(
                success=True,
                data=events,
                error=None,
                tool_name="execute_oc_get_pod_events",
                namespace=namespace,
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
        description="""Get recent OpenShift events from a namespace for cluster activity analysis.

        Purpose: View recent cluster events to understand what happened in a namespace.

        Args:
        - namespace: OpenShift namespace to query
        - tail: Number of recent events to return (optional, uses config default)

        Returns: ToolResult with List[OpenShiftEvent] containing:
        - type: Normal or Warning event severity
        - reason: Event code (Scheduled, Failed, FailedScheduling, etc.)
        - message: Human-readable event description
        - object: Name of object that generated the event
        - count: Number of times this event occurred

        Features:
        - Prioritizes Warning events over Normal events
        - Configurable event count limit from LOG_COLLECTION settings
        - Returns empty list if no events found (not an error)

        When to use:
        - Understand recent activity in a namespace during alert investigation
        - Look for Warning events that may indicate problems
        - Get context about what operations occurred before an alert
        - Check for patterns in event frequency and types

        Example: FailedScheduling events may indicate resource constraints
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployment_events,
        name="execute_oc_get_deployment_events",
        description="""Get events specifically related to a deployment for targeted debugging.

        Purpose: View deployment-specific events to understand scaling and rollout issues.

        Args:
        - deployment_name: Name of the deployment to analyze
        - namespace: OpenShift namespace

        Returns: ToolResult with List[OpenShiftEvent] containing:
        - type: Normal or Warning event type
        - reason: Event code (ScalingReplicaSet, FailedCreate, DeploymentRollback, etc.)
        - message: Human-readable event message
        - object: Object name that generated the event
        - count: Number of times this event occurred

        Features:
        - Filters events to show only deployment-related activity
        - Returns empty list if no events found (not an error)
        - Focuses on scaling and rollout events for targeted analysis

        When to use:
        - Investigate deployment scaling issues or stuck rollouts
        - Understand why a deployment isn't reaching desired replicas
        - Check for deployment-specific failures or warnings
        - Analyze rollout history and scaling patterns

        Example: ScalingReplicaSet events show successful/failed scaling operations
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_pod_events,
        name="execute_oc_get_pod_events",
        description="""Get events specifically related to a pod for debugging and troubleshooting.

        Purpose: View pod-specific event history to understand failures and state changes.

        Args:
        - pod_name: Pod name (supports partial names like "api-server")
        - namespace: OpenShift namespace

        Returns: ToolResult with List[OpenShiftEvent] containing:
        - type: Normal or Warning event severity
        - reason: Event code (Scheduled, Failed, FailedScheduling, Pulled, etc.)
        - message: Human-readable event description
        - object: Object that generated the event
        - count: Number of times event occurred

        Features:
        - Supports partial pod names (auto-matches to full name)
        - Returns empty list if no events found (not an error)
        - Filters events specific to the pod for focused debugging

        When to use:
        - Investigate why a pod failed to start or is stuck
        - Understand scheduling issues or resource problems
        - Track pod lifecycle events and state transitions
        - Debug container startup failures

        Example: Pod stuck in Pending → check for FailedScheduling events
        """,
    ),
]
