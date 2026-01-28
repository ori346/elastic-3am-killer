"""
Context management tools for OpenShift Alert Remediation Specialist.

This module provides tools for reading alert diagnostics and writing remediation plans
to shared context for coordination between agents.
"""

from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

from .models import ToolResult
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
        ToolResult with dict containing alert diagnostics on success
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

        # Build response dict (same structure as before)
        diagnostics_dict = {
            "namespace": namespace,
            "alert_name": alert_name,
            "alert_diagnostics": alert_diagnostics,
            "alert_status": alert_status,
            "recommendation": recommendation,
        }

        return ToolResult(
            success=True,
            data=diagnostics_dict,
            error=None,
            tool_name="read_alert_diagnostics_data",
            namespace=namespace if namespace != "unknown" else None,
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
        ToolResult with dict containing plan metadata on success
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

        # Store remediation plan (existing logic)
        plan = {"explanation": explanation, "commands": commands}
        async with ctx.store.edit_state() as ctx_state:
            ctx_state["state"]["remediation_plan"] = plan

        # Build response with metadata
        plan_metadata = {
            "plan_stored": True,
            "explanation": explanation,
            "commands_count": len(commands),
            "commands": commands,
            "next_step": "Handoff to Workflow Coordinator for execution - This is MANDATORY",
        }

        return ToolResult(
            success=True,
            data=plan_metadata,
            error=None,
            tool_name="write_remediation_plan",
            namespace=None,  # Context tools are not namespace-specific
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
        description="""Read alert information from shared context with structured output.

        Purpose: Retrieve alert information to understand what needs to be remediated.

        Inputs: None - reads from context

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: dict with alert diagnostics on success, None on error
        - error: ToolError with type, message, recoverable, suggestion on failure

        Alert diagnostics dict contains:
        - namespace (str): The namespace where the alert originated
        - alert_name (str): The name of the alert
        - alert_diagnostics (str): Diagnostic text describing the alert
        - alert_status (str): Current status of the alert
        - recommendation (str): Diagnose agent recommendations

        Usage:
        result = read_alert_diagnostics_data(ctx)
        if result.success:
            alert_data = result.data
            namespace = alert_data["namespace"]
            alert_name = alert_data["alert_name"]
            diagnostics = alert_data["alert_diagnostics"]
        else:
            if result.error.type == ErrorType.NOT_FOUND:
                # No alert data in context - coordinate with Workflow Coordinator
                pass

        When to call: FIRST in Step 0 to understand the alert before investigation
        """,
    ),
    FunctionTool.from_defaults(
        fn=write_remediation_plan,
        name="write_remediation_plan",
        description="""Write remediation plan with validated commands to shared context.

        Purpose: Create executable remediation commands and explanation for the Workflow Coordinator to execute.

        Required Inputs:
        - explanation (str): Brief explanation of the issue and why the commands will fix it
          Example: "backend has 128Mi memory limit causing OOMKilled. Increasing to 512Mi."
        - commands (list[str]): List of EXECUTABLE oc commands (NOT descriptions)
          Must be valid shell commands that modify cluster state

        Returns: ToolResult with:
        - success: bool - whether operation succeeded
        - data: dict with plan metadata on success, None on error
        - error: ToolError with type, message, recoverable, suggestion on failure

        Plan metadata dict contains:
        - plan_stored: bool - Whether plan was successfully stored
        - explanation: str - The explanation provided
        - commands_count: int - Number of commands in the plan
        - commands: list[str] - The validated commands
        - next_step: str - Instructions for next workflow step

        Usage:
        result = write_remediation_plan(
            ctx, "Fix CPU limits", ["oc set resources deployment web --limits=cpu=500m"]
        )
        if result.success:
            plan_data = result.data
            commands_count = plan_data["commands_count"]
            next_step = plan_data["next_step"]
        else:
            if result.error.type == ErrorType.SYNTAX:
                # Invalid commands provided
                suggestion = result.error.suggestion

        NEXT STEP AFTER THIS TOOL: You MUST immediately handoff to "Workflow Coordinator" - MANDATORY

        CRITICAL RULES:
        - Commands MUST be executable shell commands, NOT descriptions
        - Each command must be a complete, valid oc command
        - Use proper format: oc set resources deployment <name> -n <namespace> --limits=cpu=X,memory=Y --requests=cpu=X,memory=Y
        - DO NOT use multiple --limits or --requests flags in one command
        - DO NOT use descriptive text like "Increase memory" - use actual commands

        CORRECT EXAMPLE:
        write_remediation_plan(
            explanation="Frontend has 128Mi memory causing OOMKilled. Increasing to 512Mi.",
            commands=[
                "oc set resources deployment frontend -n awesome-app --limits=cpu=500m,memory=512Mi --requests=cpu=250m,memory=256Mi"
            ]
        )

        WRONG EXAMPLES:
        ❌ commands=["Increase CPU and memory"]  # Not a command
        ❌ commands=["oc set resources --limits=cpu=1000m --limits=memory=512Mi"]  # Duplicate flags
        ❌ commands=["oc set resources deployment frontend --limits=cpu=500m"]  # Missing namespace

        When to call: In Step 3, after investigating with oc tools

        CRITICAL: After calling this tool, you MUST call handoff tool immediately in Step 4 - MANDATORY
        """,
    ),
]
