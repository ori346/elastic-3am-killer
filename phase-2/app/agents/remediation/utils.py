"""
Utility functions for OpenShift command execution.

This module provides common utilities for executing oc commands and processing output
that are shared across different tool modules.
"""

import subprocess

from configs import TIMEOUTS


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
    timeout: int = TIMEOUTS.oc_command_default
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
