"""
Utility functions for OpenShift command execution.

This module provides common utilities for executing oc commands and processing output
that are shared across different tool modules. Includes support for the unified ToolResult system.
"""

import subprocess
from typing import Dict, List, Optional

from configs import TIMEOUTS

from .models import ErrorType, ToolError


def run_oc_command(
    command: list[str], timeout: int = TIMEOUTS.oc_command_default
) -> tuple[int, str, str]:
    """
    Execute an oc command with standard error handling.

    Args:
        command: List of command arguments (e.g., ["oc", "get", "pods"])
        timeout: Timeout in seconds (default: from config)

    Returns:
        Tuple of (returncode, stdout, stderr)

    Raises:
        subprocess.TimeoutExpired: If command times out
        Exception: For other errors
    """
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def find_pod_by_name(
    pod_name: str, namespace: str, timeout: int = TIMEOUTS.oc_command_default
) -> tuple[bool, str]:
    """
    Find a pod by exact or partial name match.

    Args:
        pod_name: Name of the pod (can be partial)
        namespace: OpenShift namespace
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, pod_name or error_message)
    """
    try:
        list_result = subprocess.run(
            [
                "oc",
                "get",
                "pods",
                "-n",
                namespace,
                "-o",
                "jsonpath={.items[*].metadata.name}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if list_result.returncode == 0:
            all_pods = list_result.stdout.split()
            # Try exact match first
            if pod_name in all_pods:
                return True, pod_name
            else:
                # Try partial match (e.g., "frontend" matches "frontend-698f45c955-hbkjz")
                matching_pods = [p for p in all_pods if p.startswith(pod_name)]
                if matching_pods:
                    actual_pod_name = matching_pods[0]  # Use first match
                    print(
                        f"Found pod '{actual_pod_name}' matching partial name '{pod_name}'"
                    )
                    return True, actual_pod_name
                else:
                    return (
                        False,
                        f"No pod found matching '{pod_name}' in namespace '{namespace}'. It might be that the deployment doesn't have active pods.",
                    )
        else:
            # Fallback to trying exact name
            return True, pod_name
    except subprocess.TimeoutExpired:
        return False, f"Timeout finding pod {pod_name}"
    except Exception as e:
        return False, f"Error finding pod: {str(e)}"


def compact_output(text: str) -> str:
    """
    Compact whitespace in text while preserving table structure.

    Args:
        text: Input text with potentially excessive whitespace

    Returns:
        Compacted text with single spaces
    """
    lines = text.strip().split("\n")
    compacted_lines = []
    for line in lines:
        # Replace multiple spaces with single space while preserving table structure
        compacted = " ".join(line.split())
        compacted_lines.append(compacted)
    return "\n".join(compacted_lines)


def parse_describe_field(lines: list[str], field_name: str) -> str:
    """
    Extract a single field value from oc describe output.

    Args:
        lines: Lines from oc describe output
        field_name: Name of the field to extract (e.g., "Service Account")

    Returns:
        Field value or empty string if not found
    """
    for line in lines:
        if line.startswith(f"{field_name}:"):
            return line.split(":", 1)[1].strip()
    return ""


def parse_describe_section(lines: list[str], section_name: str) -> list[str]:
    """
    Extract a section from oc describe output.

    Args:
        lines: Lines from oc describe output
        section_name: Name of the section (e.g., "Containers", "Conditions")

    Returns:
        List of lines in that section (without the section header)
    """
    section_lines = []
    in_section = False

    for line in lines:
        # Section starts
        if line.startswith(f"{section_name}:"):
            in_section = True
            continue

        # Section ends (next top-level section starts)
        if in_section and line and not line.startswith(" "):
            break

        # Collect section content
        if in_section:
            section_lines.append(line)

    return section_lines


def execute_oc_command_with_error_handling(
    command: list[str],
    success_message_template: str,
    error_message_template: str,
    timeout: int = TIMEOUTS.oc_command_default,
) -> str:
    """
    Execute oc command with standardized error handling.

    Args:
        command: List of command arguments (e.g., ["oc", "get", "pods"])
        success_message_template: Template for success message (use {stdout} placeholder)
        error_message_template: Template for error message (use {stderr} placeholder)
        timeout: Timeout in seconds

    Returns:
        Formatted success or error message
    """
    try:
        returncode, stdout, stderr = run_oc_command(command, timeout)
        if returncode == 0:
            return success_message_template.format(stdout=compact_output(stdout))
        else:
            return error_message_template.format(stderr=stderr)
    except subprocess.TimeoutExpired:
        cmd_str = " ".join(command)
        return f"Timeout executing {cmd_str}"
    except Exception as e:
        cmd_str = " ".join(command)
        return f"Error executing {cmd_str}: {str(e)}"


# ===== ToolResult System Utilities =====


def classify_oc_error(stderr: str) -> ErrorType:
    """
    Classify oc command errors into structured types for programmatic handling.
    """
    stderr_lower = stderr.lower()

    # Define error patterns with their corresponding types
    # Order matters: more specific patterns should come first
    error_patterns = [
        # CONFIGURATION patterns - specific config-related errors should come before NOT_FOUND
        (
            ["configmap", "secret not found in configuration", "invalid configuration"],
            ErrorType.CONFIGURATION,
        ),
        # NOT_FOUND patterns - including server resource type errors
        (
            ["not found", "no resources found", "doesn't have a resource type"],
            ErrorType.NOT_FOUND,
        ),
        # TIMEOUT patterns - including various timeout formats
        (["timeout", "timed out"], ErrorType.TIMEOUT),
        # SYNTAX patterns - including parsing errors and unknown commands
        (
            ["invalid", "syntax", "malformed", "parsing", "unknown command"],
            ErrorType.SYNTAX,
        ),
        # PERMISSION patterns
        (["forbidden", "unauthorized"], ErrorType.PERMISSION),
        # NETWORK patterns - including connection variants
        (["connection", "connect", "network", "unreachable"], ErrorType.NETWORK),
        # RESOURCE_LIMIT patterns
        (["quota", "limit"], ErrorType.RESOURCE_LIMIT),
        # CONFIGURATION patterns (general config errors)
        (["config", "configuration"], ErrorType.CONFIGURATION),
    ]

    for patterns, error_type in error_patterns:
        if any(pattern in stderr_lower for pattern in patterns):
            return error_type

    return ErrorType.UNKNOWN


def get_error_suggestion(
    error_type: ErrorType,
    namespace: Optional[str] = None,
    resource: Optional[str] = None,
) -> str:
    """
    Get specific suggestions based on error type and context.
    """
    suggestions = {
        ErrorType.NOT_FOUND: "Verify that the resource exists and the name/namespace are correct",
        ErrorType.PERMISSION: "Check that you have sufficient permissions for this operation",
        ErrorType.NETWORK: "Verify cluster connectivity and authentication",
        ErrorType.TIMEOUT: "Check cluster responsiveness and consider retrying",
        ErrorType.SYNTAX: "Verify command syntax and cluster version compatibility",
        ErrorType.RESOURCE_LIMIT: "Check resource quotas and limits in the namespace",
        ErrorType.CONFIGURATION: "Review configuration settings and verify correctness",
        ErrorType.UNKNOWN: "Check command logs and cluster status for more details",
    }

    suggestion = suggestions.get(error_type, "Contact administrator for assistance")

    # Add context-specific details
    if namespace and error_type in [ErrorType.NOT_FOUND, ErrorType.PERMISSION]:
        suggestion += (
            f" in namespace '{namespace}'"
            if error_type == ErrorType.NOT_FOUND
            else f" for namespace '{namespace}'"
        )

    if resource and error_type == ErrorType.NOT_FOUND:
        suggestion += (
            f". Consider checking if {resource} needs to be created or scaled up."
        )

    return suggestion


def extract_container_state(container_status: Dict) -> str:
    """Extract container state from OpenShift container status."""
    state = container_status.get("state", {})
    state_types = ["running", "waiting", "terminated"]
    return next(
        (state_type for state_type in state_types if state_type in state), "unknown"
    )


def format_ready_status(container_statuses: List[Dict]) -> str:
    """Format container ready status as ratio string."""
    if not container_statuses:
        return "0/0"

    ready_count = sum(1 for cs in container_statuses if cs.get("ready", False))
    return f"{ready_count}/{len(container_statuses)}"


def create_tool_error(
    error_type: ErrorType,
    message: str,
    tool_name: str,
    recoverable: bool = False,
    suggestion: Optional[str] = None,
    raw_output: Optional[str] = None,
    namespace: Optional[str] = None,
) -> ToolError:
    """Create a ToolError with all necessary context."""
    if suggestion is None:
        suggestion = get_error_suggestion(error_type, namespace)

    return ToolError(
        type=error_type,
        message=message,
        recoverable=recoverable,
        suggestion=suggestion,
        raw_output=raw_output,
        tool_name=tool_name,
        namespace=namespace,
    )


# Backward compatibility alias - will be removed after tool functions are updated
def create_error_result(
    error_type: ErrorType,
    message: str,
    tool_name: str,
    recoverable: bool = False,
    suggestion: Optional[str] = None,
    raw_output: Optional[str] = None,
    namespace: Optional[str] = None,
) -> ToolError:
    """Backward compatibility alias for create_tool_error."""
    return create_tool_error(
        error_type=error_type,
        message=message,
        tool_name=tool_name,
        recoverable=recoverable,
        suggestion=suggestion,
        raw_output=raw_output,
        namespace=namespace,
    )
