"""
Pydantic models for structured tool outputs and error handling.

This module provides the unified data models for the OpenShift remediation tools,
combining structured data outputs and structured error responses
into a comprehensive ToolResult system.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Error Handling Models
class ErrorType(str, Enum):
    """Types of tool execution errors for programmatic handling"""

    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    SYNTAX = "syntax"
    NETWORK = "network"
    RESOURCE_LIMIT = "resource_limit"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class ToolResult(BaseModel):
    """Base class for tool execution results"""

    tool_name: str = Field(description="Name of the tool that was executed")
    namespace: Optional[str] = Field(None, description="Target namespace if applicable")

    def __str__(self) -> str:
        """Ultra-compact string representation without any whitespace to reduce LLM tokens."""
        return self.model_dump_json(exclude_unset=True, exclude_none=True)


class ToolError(ToolResult):
    """Structured error information with recovery guidance"""

    type: ErrorType = Field(description="Category of error for programmatic handling")
    message: str = Field(description="Human readable error description")
    recoverable: bool = Field(description="Whether this error can be retried")
    suggestion: str = Field(description="Recommended action to resolve the error")
    raw_output: Optional[str] = Field(
        None, description="Original command output for debugging"
    )


# Deployment Models
class DeploymentCondition(BaseModel):
    """Deployment condition information"""

    type: str = Field(
        description="Condition type: Available, Progressing, ReplicaFailure"
    )
    status: str = Field(description="Condition status: True, False, Unknown")
    reason: Optional[str] = Field(None, description="Reason for condition")
    message: Optional[str] = Field(None, description="Human readable message")


class ContainerResources(BaseModel):
    """Container resource information using dict storage"""

    name: str = Field(description="Container name")
    resources: Dict[str, Any] = Field(
        default_factory=dict,
        description="Resource limits and requests structure from OpenShift spec",
    )


class DeploymentResources(ToolResult):
    """Deployment resource information focused on CPU, memory and replicas"""

    tool_name: str = Field(
        default="oc_get_deployment_resources", description="Name of the tool"
    )
    name: str = Field(description="Deployment name")
    ready_replicas: int = Field(0, description="Number of ready replicas")
    desired_replicas: int = Field(description="Number of desired replicas")
    containers: List[ContainerResources] = Field(
        default_factory=list, description="Per-container resource information"
    )


# Event Models
class EventType(str, Enum):
    """OpenShift event types"""

    NORMAL = "Normal"
    WARNING = "Warning"


class OpenShiftEvent(BaseModel):
    """OpenShift event information"""

    type: EventType = Field(description="Event severity: Normal or Warning")
    reason: str = Field(
        description="Event reason code (e.g., FailedScheduling, Pulled)"
    )
    message: str = Field(description="Human readable event message")
    object: str = Field(description="Object that generated the event")
    count: int = Field(1, description="Number of times this event occurred")


class OpenShiftEvents(ToolResult):
    """Collection of OpenShift events from a namespace or resource"""

    tool_name: str = Field(default="oc_get_events", description="Name of the tool")
    events: List[OpenShiftEvent] = Field(
        default_factory=list, description="List of retrieved OpenShift events"
    )


# Log Models
class LogEntry(BaseModel):
    """Individual log entry with metadata"""

    level: Optional[str] = Field(
        None, description="Log level: ERROR, WARN, INFO, DEBUG"
    )
    message: str = Field(description="Log message content")
    container: Optional[str] = Field(
        None, description="Container that generated the log"
    )


# Context Management Results
class AlertDiagnosticsResult(ToolResult):
    """Result of reading alert diagnostics from context"""

    tool_name: str = Field(
        default="read_alert_diagnostics_data", description="Name of the tool"
    )
    alert: Dict[str, str] = Field(description="Alert information")
    diagnostics_suggestions: str = Field(
        description="Diagnostic information and suggestions"
    )
    logs: List[str] = Field(description="Relevant log entries")
    remediation_reports: Optional[List[Dict[str, str]]] = Field(
        default=None, description="Previous remediation attempts"
    )


class RemediationPlanResult(ToolResult):
    """Result of writing a remediation plan to context"""

    plan_written: bool = Field(description="Whether the plan was written to context")
    next_step: str = Field(description="Next step in the workflow")


# Streamlined Output Models (no None fields)
class DeploymentSummary(BaseModel):
    """Deployment summary without optional None fields"""

    name: str = Field(description="Deployment name")
    ready_replicas: int = Field(description="Number of ready replicas")
    desired_replicas: int = Field(description="Number of desired replicas")
    available_replicas: int = Field(description="Number of available replicas")
    updated_replicas: int = Field(description="Number of updated replicas")


class PodSummary(BaseModel):
    """Pod summary without optional None fields"""

    name: str = Field(description="Pod name")
    status: str = Field(description="Pod phase")
    ready: str = Field(description="Ready containers ratio")
    restarts: int = Field(description="Total restarts")
    age: str = Field(description="Human readable age")


# Streamlined Result Types
class DeploymentListResult(ToolResult):
    """Streamlined deployment listing result"""

    tool_name: str = Field(default="oc_get_deployments", description="Name of the tool")
    deployments: List[DeploymentSummary] = Field(description="List of deployments")


class PodListResult(ToolResult):
    """Streamlined pod listing result"""

    tool_name: str = Field(default="oc_get_pods", description="Name of the tool")
    pods: List[PodSummary] = Field(description="List of pods")


class LogResult(ToolResult):
    """Streamlined log response"""

    tool_name: str = Field(default="oc_get_logs", description="Name of the tool")
    pod_name: str = Field(description="Pod name")
    total_lines: int = Field(description="Number of log lines")
    entries: List[LogEntry] = Field(default_factory=list, description="Log entries")


# Enhanced Detailed Models for Debugging
class ContainerDetail(BaseModel):
    """Enhanced container information for debugging"""

    # Basic container information
    name: str = Field(description="Container name")
    image: str = Field(description="Container image with tag")
    ready: bool = Field(description="Whether container is ready")
    restart_count: int = Field(description="Number of container restarts")
    state: str = Field(description="Container state: running, waiting, terminated")

    # Resource Information (debugging resource issues)
    limits: Optional[Dict[str, str]] = Field(
        None, description="Resource limits (CPU, memory)"
    )
    requests: Optional[Dict[str, str]] = Field(
        None, description="Resource requests (CPU, memory)"
    )

    # Health Check Configuration (debugging probe failures)
    liveness_probe: Optional[Dict[str, Any]] = Field(
        None, description="Liveness probe configuration"
    )
    readiness_probe: Optional[Dict[str, Any]] = Field(
        None, description="Readiness probe configuration"
    )

    # State Details (debugging crashes/failures)
    exit_code: Optional[int] = Field(
        None, description="Container exit code if terminated"
    )
    termination_reason: Optional[str] = Field(
        None, description="Reason for container termination"
    )
    termination_message: Optional[str] = Field(
        None, description="Container termination message"
    )

    # Configuration (debugging env/networking issues)
    ports: List[Dict[str, Any]] = Field(
        default_factory=list, description="Container port configurations"
    )
    environment: List[Dict[str, str]] = Field(
        default_factory=list, description="Environment variables"
    )


class PodDetail(BaseModel):
    """Enhanced pod information for debugging"""

    # Basic pod information
    name: str = Field(description="Pod name")
    status: str = Field(description="Pod phase")
    ready: str = Field(description="Ready containers ratio")
    restarts: int = Field(description="Total container restarts")

    # Network Information (debugging connectivity)
    pod_ip: Optional[str] = Field(None, description="Pod IP address")
    host_ip: Optional[str] = Field(None, description="Host IP address")

    # Configuration Context (debugging scheduling/security)
    labels: Dict[str, str] = Field(default_factory=dict, description="Pod labels")
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Pod annotations"
    )
    service_account: Optional[str] = Field(
        None, description="Service account used by pod"
    )
    security_context: Optional[Dict[str, Any]] = Field(
        None, description="Pod security context"
    )

    # Ownership (debugging creation/lifecycle)
    owner_references: List[Dict[str, str]] = Field(
        default_factory=list, description="Pod owner references"
    )


class PodDetailedResult(ToolResult):
    """Detailed pod information for debugging"""

    tool_name: str = Field(default="oc_describe_pod", description="Name of the tool")
    pod: PodDetail = Field(description="Detailed pod information")
    containers: List[ContainerDetail] = Field(
        default_factory=list, description="Detailed container information"
    )


class DeploymentDetail(ToolResult):
    """Enhanced deployment information for debugging"""

    tool_name: str = Field(
        default="oc_describe_deployment", description="Name of the tool"
    )

    # Basic deployment information
    name: str = Field(description="Deployment name")
    ready_replicas: int = Field(0, description="Number of ready replicas")
    desired_replicas: int = Field(description="Number of desired replicas")
    available_replicas: int = Field(0, description="Number of available replicas")
    updated_replicas: int = Field(0, description="Number of updated replicas")
    unavailable_replicas: int = Field(0, description="Number of unavailable replicas")

    # Strategy Details (debugging rollout problems)
    strategy_type: Optional[str] = Field(None, description="Deployment strategy type")
    max_surge: Optional[str] = Field(None, description="Maximum surge during rollout")
    max_unavailable: Optional[str] = Field(
        None, description="Maximum unavailable during rollout"
    )

    # Rollout Status (debugging stuck deployments)
    observed_generation: Optional[int] = Field(
        None, description="Observed generation for rollout tracking"
    )
    progress_deadline_seconds: Optional[int] = Field(
        None, description="Progress deadline for rollouts"
    )

    # Configuration Context
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Deployment labels"
    )
    selector_labels: Dict[str, str] = Field(
        default_factory=dict, description="Pod selector labels"
    )

    # Conditions (enhanced with more detail)
    conditions: List[DeploymentCondition] = Field(
        default_factory=list, description="Deployment conditions"
    )
