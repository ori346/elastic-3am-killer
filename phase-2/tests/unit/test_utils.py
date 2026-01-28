"""
import pytest

Tests for utility functions used by ToolResult system.

This module tests utility functions for command execution, output parsing,
and text formatting that are shared across different tool modules.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from agents.remediation.utils import (
    compact_output,
    execute_oc_command_with_error_handling,
    find_pod_by_name,
    parse_describe_field,
    parse_describe_section,
    run_oc_command,
)


class TestRunOcCommand:
    """Test oc command execution utility"""

    @patch("subprocess.run")
    def test_run_oc_command_success(self, mock_run):
        """Test successful oc command execution"""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="command output", stderr=""
        )

        returncode, stdout, stderr = run_oc_command(["oc", "get", "pods"])

        assert returncode == 0
        assert stdout == "command output"
        assert stderr == ""
        mock_run.assert_called_once_with(
            ["oc", "get", "pods"],
            capture_output=True,
            text=True,
            timeout=30,  # Default timeout from config
        )

    @patch("subprocess.run")
    def test_run_oc_command_failure(self, mock_run):
        """Test failed oc command execution"""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error: pods not found"
        )

        returncode, stdout, stderr = run_oc_command(["oc", "get", "pods"])

        assert returncode == 1
        assert stdout == ""
        assert stderr == "Error: pods not found"

    @patch("subprocess.run")
    def test_run_oc_command_custom_timeout(self, mock_run):
        """Test oc command with custom timeout"""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        run_oc_command(["oc", "logs", "pod"], timeout=60)

        mock_run.assert_called_once_with(
            ["oc", "logs", "pod"], capture_output=True, text=True, timeout=60
        )

    @patch("subprocess.run")
    def test_run_oc_command_timeout_exception(self, mock_run):
        """Test oc command timeout exception propagation"""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "pods"], timeout=30
        )

        with pytest.raises(subprocess.TimeoutExpired):
            run_oc_command(["oc", "get", "pods"])


class TestFindPodByName:
    """Test pod name finding utility"""

    @patch("subprocess.run")
    def test_find_pod_by_name_exact_match(self, mock_run):
        """Test finding pod with exact name match"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="frontend-698f45c955-hbkjz backend-db-567890abcd-xyz12",
            stderr="",
        )

        success, pod_name = find_pod_by_name("frontend-698f45c955-hbkjz", "test-ns")

        assert success is True
        assert pod_name == "frontend-698f45c955-hbkjz"
        mock_run.assert_called_once_with(
            [
                "oc",
                "get",
                "pods",
                "-n",
                "test-ns",
                "-o",
                "jsonpath={.items[*].metadata.name}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("subprocess.run")
    def test_find_pod_by_name_partial_match(self, mock_run):
        """Test finding pod with partial name match"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="frontend-698f45c955-hbkjz backend-db-567890abcd-xyz12",
            stderr="",
        )

        success, pod_name = find_pod_by_name("frontend", "test-ns")

        assert success is True
        assert pod_name == "frontend-698f45c955-hbkjz"

    @patch("subprocess.run")
    def test_find_pod_by_name_no_match(self, mock_run):
        """Test finding pod with no match"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="frontend-698f45c955-hbkjz backend-db-567890abcd-xyz12",
            stderr="",
        )

        success, message = find_pod_by_name("missing-pod", "test-ns")

        assert success is False
        assert "No pod found matching 'missing-pod'" in message
        assert "test-ns" in message

    @patch("subprocess.run")
    def test_find_pod_by_name_multiple_partial_matches(self, mock_run):
        """Test finding pod returns first match when multiple partial matches"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="frontend-v1-abc123 frontend-v2-def456 backend-xyz789",
            stderr="",
        )

        success, pod_name = find_pod_by_name("frontend", "test-ns")

        assert success is True
        assert pod_name == "frontend-v1-abc123"  # First match

    @patch("subprocess.run")
    def test_find_pod_by_name_command_failure(self, mock_run):
        """Test finding pod when oc command fails"""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error: namespace not found"
        )

        success, pod_name = find_pod_by_name("test-pod", "missing-ns")

        assert success is True  # Fallback to trying exact name
        assert pod_name == "test-pod"

    @patch("subprocess.run")
    def test_find_pod_by_name_timeout(self, mock_run):
        """Test finding pod with timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "pods"], timeout=30
        )

        success, message = find_pod_by_name("test-pod", "test-ns")

        assert success is False
        assert "Timeout finding pod" in message

    @patch("subprocess.run")
    def test_find_pod_by_name_exception(self, mock_run):
        """Test finding pod with unexpected exception"""
        mock_run.side_effect = Exception("Unexpected error")

        success, message = find_pod_by_name("test-pod", "test-ns")

        assert success is False
        assert "Error finding pod" in message

    @pytest.mark.parametrize(
        "search_name,expected_match",
        [
            ("frontend", "frontend-698f45c955-hbkjz"),
            ("backend", "backend-db-567890abcd-xyz12"),
            ("no-match", None),
        ],
    )
    def test_find_pod_by_name_parametrized(self, search_name, expected_match):
        """Test pod name finding with parametrized cases"""
        # Mock the subprocess response
        all_pods = "frontend-698f45c955-hbkjz backend-db-567890abcd-xyz12"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=all_pods, stderr="")

            success, result = find_pod_by_name(search_name, "test-ns")

            if expected_match:
                assert success is True
                assert result == expected_match
            else:
                assert success is False
                assert f"No pod found matching '{search_name}'" in result


class TestTextProcessingUtilities:
    """Test text processing and parsing utilities"""

    def test_compact_output_basic(self):
        """Test basic whitespace compaction"""
        input_text = "NAME     READY   STATUS    RESTARTS   AGE\nfrontend   1/1     Running   0          5m"
        expected = "NAME READY STATUS RESTARTS AGE\nfrontend 1/1 Running 0 5m"

        result = compact_output(input_text)
        assert result == expected

    def test_compact_output_multiple_spaces(self):
        """Test compaction of multiple spaces"""
        input_text = (
            "pod1     running      0       5m\npod2       failed        3         1h"
        )
        expected = "pod1 running 0 5m\npod2 failed 3 1h"

        result = compact_output(input_text)
        assert result == expected

    def test_compact_output_tabs_and_spaces(self):
        """Test compaction with mixed tabs and spaces"""
        input_text = "header1\t\theader2   header3\nvalue1\t  value2     value3"
        expected = "header1 header2 header3\nvalue1 value2 value3"

        result = compact_output(input_text)
        assert result == expected

    def test_compact_output_preserve_single_spaces(self):
        """Test that single spaces are preserved"""
        input_text = "normal text with single spaces"
        expected = "normal text with single spaces"

        result = compact_output(input_text)
        assert result == expected

    def test_compact_output_empty_lines(self):
        """Test handling of empty lines"""
        input_text = "line1\n\nline3\n   \nline5"
        expected = "line1\n\nline3\n\nline5"

        result = compact_output(input_text)
        assert result == expected

    def test_parse_describe_field_found(self):
        """Test parsing field from oc describe output"""
        describe_lines = [
            "Name:         test-pod",
            "Namespace:    default",
            "Priority:     0",
            "Service Account:  my-service-account",
            "Node:         worker-1",
        ]

        result = parse_describe_field(describe_lines, "Service Account")
        assert result == "my-service-account"

    def test_parse_describe_field_not_found(self):
        """Test parsing field that doesn't exist"""
        describe_lines = ["Name:         test-pod", "Namespace:    default"]

        result = parse_describe_field(describe_lines, "Missing Field")
        assert result == ""

    def test_parse_describe_field_multiple_colons(self):
        """Test parsing field with multiple colons in value"""
        describe_lines = ["Image:        registry.example.com:5000/app:latest"]

        result = parse_describe_field(describe_lines, "Image")
        assert result == "registry.example.com:5000/app:latest"

    def test_parse_describe_section_found(self):
        """Test parsing section from oc describe output"""
        describe_lines = [
            "Name:         test-pod",
            "Containers:",
            "  frontend:",
            "    Image:      nginx:1.20",
            "    State:      Running",
            "  backend:",
            "    Image:      python:3.9",
            "Conditions:",
            "  Type   Status",
            "  Ready  True",
        ]

        result = parse_describe_section(describe_lines, "Containers")
        expected = [
            "  frontend:",
            "    Image:      nginx:1.20",
            "    State:      Running",
            "  backend:",
            "    Image:      python:3.9",
        ]
        assert result == expected

    def test_parse_describe_section_not_found(self):
        """Test parsing section that doesn't exist"""
        describe_lines = ["Name:         test-pod", "Namespace:    default"]

        result = parse_describe_section(describe_lines, "Missing Section")
        assert result == []

    def test_parse_describe_section_empty_section(self):
        """Test parsing empty section"""
        describe_lines = [
            "Name:         test-pod",
            "Empty Section:",
            "Next Section:",
            "  Some content",
        ]

        result = parse_describe_section(describe_lines, "Empty Section")
        assert result == []

    def test_parse_describe_section_last_section(self):
        """Test parsing the last section in output"""
        describe_lines = [
            "Name:         test-pod",
            "Events:",
            "  Type    Reason     Message",
            "  Normal  Scheduled  Successfully assigned pod",
        ]

        result = parse_describe_section(describe_lines, "Events")
        expected = [
            "  Type    Reason     Message",
            "  Normal  Scheduled  Successfully assigned pod",
        ]
        assert result == expected


class TestExecuteOcCommandWithErrorHandling:
    """Test the high-level command execution with error handling"""

    @patch("agents.remediation.utils.run_oc_command")
    def test_execute_oc_command_success(self, mock_run_oc):
        """Test successful command execution with formatting"""
        mock_run_oc.return_value = (0, "pod1    running\npod2   failed", "")

        result = execute_oc_command_with_error_handling(
            ["oc", "get", "pods"],
            "Pods retrieved:\n{stdout}",
            "Failed to get pods: {stderr}",
        )

        expected = "Pods retrieved:\npod1 running\npod2 failed"
        assert result == expected

    @patch("agents.remediation.utils.run_oc_command")
    def test_execute_oc_command_failure(self, mock_run_oc):
        """Test failed command execution"""
        mock_run_oc.return_value = (1, "", "Error: pods not found")

        result = execute_oc_command_with_error_handling(
            ["oc", "get", "pods"],
            "Pods retrieved:\n{stdout}",
            "Failed to get pods: {stderr}",
        )

        assert result == "Failed to get pods: Error: pods not found"

    @patch("agents.remediation.utils.run_oc_command")
    def test_execute_oc_command_timeout(self, mock_run_oc):
        """Test command timeout handling"""
        mock_run_oc.side_effect = subprocess.TimeoutExpired(
            cmd=["oc", "get", "pods"], timeout=30
        )

        result = execute_oc_command_with_error_handling(
            ["oc", "get", "pods"], "Success: {stdout}", "Error: {stderr}"
        )

        assert "Timeout executing oc get pods" in result

    @patch("agents.remediation.utils.run_oc_command")
    def test_execute_oc_command_exception(self, mock_run_oc):
        """Test unexpected exception handling"""
        mock_run_oc.side_effect = Exception("Unexpected error")

        result = execute_oc_command_with_error_handling(
            ["oc", "describe", "pod", "test"], "Success: {stdout}", "Error: {stderr}"
        )

        assert "Error executing oc describe pod test" in result
        assert "Unexpected error" in result

    @patch("agents.remediation.utils.run_oc_command")
    def test_execute_oc_command_custom_timeout(self, mock_run_oc):
        """Test command with custom timeout"""
        mock_run_oc.return_value = (0, "success", "")

        execute_oc_command_with_error_handling(
            ["oc", "logs", "pod"], "Logs: {stdout}", "Error: {stderr}", timeout=60
        )

        mock_run_oc.assert_called_once_with(["oc", "logs", "pod"], 60)


class TestConfigIntegration:
    """Test integration with configuration system"""

    def test_run_oc_command_uses_default_timeout(self):
        """Test that run_oc_command uses default timeout from config"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            run_oc_command(["oc", "get", "pods"])

            # Verify timeout from config is used (30 seconds is the default)
            call_args = mock_run.call_args
            assert call_args[1]["timeout"] == 30
