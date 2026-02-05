"""
Context management tools for OpenShift Alert Remediation Specialist.

This module provides tools for reading alert diagnostics and writing remediation plans
to shared context for coordination between agents.
"""

from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

from .models import AlertDiagnosticsResult, ToolResult, RemediationPlanResult
from .tool_tracker import reset_tool_usage_counter
from .utils import ErrorType, create_error_result

# Read-only OpenShift commands that don't change cluster state
READ_ONLY_OC_COMMANDS = (
    "oc get",
    "oc describe",
    "oc logs",
    "oc status",
    "oc observe",
    "oc explain",
)


async def read_alert_diagnostics_data(ctx: Context) -> ToolResult:
    """
    Read alert information from shared context with structured output.

    Returns:
        AlertDiagnosticsResult with alert diagnostics dict on success
    """
    try:
        state = await ctx.store.get("state")

        # Validate essential data exists
        if not state or not isinstance(state, dict):
            return create_error_result(
                error_type=ErrorType.NOT_FOUND,
                message="No alert diagnostics data found in shared context. Cannot investigate alert without information about the namespace, alert name, status, and diagnostic details.",
                tool_name="read_alert_diagnostics_data",
                suggestion="Ensure Workflow Coordinator has stored complete alert information before starting remediation investigation",
            )

        # Extract alert data with defaults for missing fields
        namespace = state.get("namespace", "unknown")
        alert_name = state.get("alert_name", "unknown")
        alert_diagnostics = state.get("alert_diagnostics", "")
        alert_status = state.get("alert_status", "unknown")
        recommendation = state.get("recommendation", "")

        # Validate that we have at least some essential data
        if (
            not namespace
            or namespace == "unknown"
            and not alert_name
            or alert_name == "unknown"
        ):
            return create_error_result(
                error_type=ErrorType.NOT_FOUND,
                message="Alert diagnostics data incomplete - missing critical namespace and alert name. Cannot target remediation efforts without knowing which namespace and specific alert to investigate.",
                tool_name="read_alert_diagnostics_data",
                suggestion="Ensure Workflow Coordinator has stored complete alert information including namespace and alert name before starting investigation",
            )

        # Build diagnostics dict
        diagnostics_dict = {
            "namespace": namespace,
            "alert_name": alert_name,
            "alert_diagnostics": alert_diagnostics,
            "alert_status": alert_status,
            "recommendation": recommendation,
        }

        return AlertDiagnosticsResult(
            tool_name="read_alert_diagnostics_data",
            namespace=namespace if namespace != "unknown" else None,
            alert_diagnostics=diagnostics_dict,
        )

    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Failed to access shared context store for alert diagnostics: {str(e)}. Cannot proceed with remediation investigation without alert information.",
            tool_name="read_alert_diagnostics_data",
            suggestion="Check context store connectivity, verify data format integrity, and ensure Workflow Coordinator has properly initialized the shared context",
        )


async def write_remediation_plan(
    ctx: Context, explanation: str, commands: list[str]
) -> ToolResult:
    """
    Write remediation plan with validated oc commands to shared context.

    Returns:
        RemediationPlanResult with plan status on success
    """
    try:
        # Existing validation logic
        if not commands:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message="No remediation commands provided. Alert remediation requires executable actions to modify cluster state and resolve the underlying issue.",
                tool_name="write_remediation_plan",
                suggestion="Provide at least one executable oc command that fixes the root cause (e.g., 'oc set resources', 'oc scale', 'oc patch')",
            )

        # Validate commands (existing logic with improved error reporting)
        invalid_commands = []
        for cmd in commands:
            if any(
                cmd.startswith(readonly_cmd) for readonly_cmd in READ_ONLY_OC_COMMANDS
            ):
                invalid_commands.append(cmd)

        if invalid_commands:
            return create_error_result(
                error_type=ErrorType.SYNTAX,
                message=f"Read-only commands cannot remediate alerts: {invalid_commands}. These commands (oc get, oc describe, oc logs, etc.) only gather information and do not modify cluster state to resolve the underlying issue.",
                tool_name="write_remediation_plan",
                suggestion="Use only state-changing commands that fix the root cause like 'oc set resources', 'oc scale', 'oc patch', 'oc rollout restart', etc.",
            )

        # Reset tool usage counter for the next invocation (existing logic)
        reset_tool_usage_counter()

        # Store remediation plan
        plan = {"explanation": explanation, "commands": commands}
        async with ctx.store.edit_state() as ctx_state:
            ctx_state["state"]["remediation_plan"] = plan

        return RemediationPlanResult(
            tool_name="write_remediation_plan",
            plan_written=True,
            next_step="Handoff to Workflow Coordinator for execution - This is MANDATORY",
        )

    except Exception as e:
        return create_error_result(
            error_type=ErrorType.UNKNOWN,
            message=f"Failed to store remediation plan in shared context: {str(e)}. Alert cannot be resolved without successful coordination between agents.",
            tool_name="write_remediation_plan",
            suggestion="Check context store connectivity, verify shared state access permissions, and ensure the remediation plan has valid format for Workflow Coordinator execution",
        )


# Tool definitions for LlamaIndex
context_tools = [
    FunctionTool.from_defaults(
        fn=read_alert_diagnostics_data,
        name="read_alert_diagnostics_data",
        description="Read alert diagnostics from shared context. Returns: AlertDiagnosticsResult with namespace, alert_name, diagnostics, status, recommendation. Use: understand alert before investigation.",
    ),
    FunctionTool.from_defaults(
        fn=write_remediation_plan,
        name="write_remediation_plan",
        description="Store validated remediation commands in shared context. Args: explanation (str) - issue description, commands (list[str]) - executable oc commands only. Returns: RemediationPlanResult with status. Use: handoff executable commands to Workflow Coordinator.",
    ),
]
