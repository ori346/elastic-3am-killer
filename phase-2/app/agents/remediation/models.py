"""
Pydantic models for structured tool outputs and error handling.

This module provides the unified data models for the OpenShift remediation tools,
combining structured data outputs and structured error responses
into a comprehensive ToolResult system.
"""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


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


class ToolError(BaseModel):
    """Structured error information with recovery guidance"""

    type: ErrorType = Field(description="Category of error for programmatic handling")
    message: str = Field(description="Human readable error description")
    recoverable: bool = Field(description="Whether this error can be retried")
    suggestion: str = Field(description="Recommended action to resolve the error")
    raw_output: Optional[str] = Field(
        None, description="Original command output for debugging"
    )


# Core Resource Models
class ResourceRequirements(BaseModel):
    """Container resource requirements (CPU and memory)"""

    cpu: Optional[str] = Field(None, description="CPU limit/request (e.g., '500m')")
    memory: Optional[str] = Field(
        None, description="Memory limit/request (e.g., '256Mi')"
    )


class ContainerInfo(BaseModel):
    """Container configuration and runtime status"""

    name: str = Field(description="Container name")
    image: str = Field(description="Container image with tag")
    ready: bool = Field(description="Whether container is ready to serve requests")
    restart_count: int = Field(0, description="Number of container restarts")
    state: str = Field(description="Container state: running, waiting, terminated")
    limits: Optional[ResourceRequirements] = Field(None, description="Resource limits")
    requests: Optional[ResourceRequirements] = Field(
        None, description="Resource requests"
    )


class PodCondition(BaseModel):
    """Pod condition information (PodScheduled, Ready, etc.)"""

    type: str = Field(
        description="Condition type: PodScheduled, Initialized, Ready, ContainersReady"
    )
    status: str = Field(description="Condition status: True, False, Unknown")
    reason: Optional[str] = Field(None, description="Reason for condition state")


class PodInfo(BaseModel):
    """Complete pod information including containers and conditions"""

    name: str = Field(description="Pod name")
    namespace: str = Field(description="Pod namespace")
    status: str = Field(
        description="Pod phase: Running, Pending, Failed, Succeeded, Unknown"
    )
    ready: str = Field(description="Ready containers ratio: '2/2', '0/1', etc.")
    restarts: int = Field(0, description="Total restarts across all containers")
    age: str = Field(description="Human readable age: '2d', '5h', '30m'")
    node: Optional[str] = Field(None, description="Node where pod is scheduled")
    service_account: str = Field(
        default="default", description="Service account used by pod"
    )
    containers: List[ContainerInfo] = Field(
        default_factory=list, description="Container details"
    )
    conditions: List[PodCondition] = Field(
        default_factory=list, description="Pod conditions"
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


class DeploymentInfo(BaseModel):
    """Deployment status and configuration information"""

    name: str = Field(description="Deployment name")
    namespace: str = Field(description="Deployment namespace")
    ready_replicas: int = Field(0, description="Number of ready replicas")
    desired_replicas: int = Field(description="Number of desired replicas")
    available_replicas: int = Field(0, description="Number of available replicas")
    updated_replicas: int = Field(0, description="Number of updated replicas")
    strategy: Optional[str] = Field(
        None, description="Deployment strategy: RollingUpdate, Recreate"
    )
    conditions: List[DeploymentCondition] = Field(
        default_factory=list, description="Deployment conditions"
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


class LogResponse(BaseModel):
    """Collection of log entries from a pod/container"""

    pod_name: str = Field(description="Pod that logs were retrieved from")
    namespace: str = Field(description="Namespace of the pod")
    container: Optional[str] = Field(
        None, description="Specific container, if filtered"
    )
    pattern_filter: Optional[str] = Field(
        None, description="Pattern used to filter logs"
    )
    total_lines: int = Field(description="Total number of log lines available")
    entries: List[LogEntry] = Field(
        default_factory=list, description="Retrieved log entries"
    )


class ToolResult(BaseModel):
    """
    Comprehensive tool execution result combining structured data and error handling.

    This unified result type provides:
    - Structured data on success
    - Structured error information on failure
    """

    success: bool = Field(description="Whether the tool executed successfully")
    data: Optional[Any] = Field(
        None, description="Structured data on success, None on error"
    )
    error: Optional[ToolError] = Field(
        None, description="Error details on failure, None on success"
    )
    tool_name: str = Field(description="Name of the tool that was executed")
    namespace: Optional[str] = Field(None, description="Target namespace if applicable")

    @model_validator(mode="after")
    def validate_success_error_consistency(self):
        """Validate that success and error fields are consistent"""
        if self.success and self.error is not None:
            raise ValueError("ToolResult cannot have success=True and an error")
        if not self.success and self.error is None:
            raise ValueError("ToolResult with success=False must have an error")
        return self

    class Config:
        # Allow Any for data field to accommodate different model types
        arbitrary_types_allowed = True

    # def __str__(self) -> str:
    #     """Human readable representation of the tool result"""
    #     if self.success:
    #         return f"ToolResult(success=True, tool={self.tool_name})"
    #     else:
    #         return f"ToolResult(success=False, tool={self.tool_name}, error={self.error.type})"

    @property
    def is_recoverable_error(self) -> bool:
        """Check if this is a recoverable error that can be retried"""
        return not self.success and self.error is not None and self.error.recoverable

    @property
    def error_type(self) -> Optional[ErrorType]:
        """Get the error type if this result represents a failure"""
        return self.error.type if not self.success and self.error else None
