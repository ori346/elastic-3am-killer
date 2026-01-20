"""
Utility functions for OpenShift command execution.

This module provides common utilities for executing oc commands and processing output
that are shared across different tool modules.
"""

import subprocess

from configs import TIMEOUTS


def run_oc_command(command: list[str], timeout: int = TIMEOUTS.oc_command_default) -> tuple[int, str, str]:
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
                        f"No pod found matching '{pod_name}' in namespace '{namespace}'",
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
