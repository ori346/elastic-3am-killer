"""
Context management tools for OpenShift remediation agent.

This module provides tools for reading alert diagnostics and writing remediation plans
to shared context for coordination between agents.
"""

import json

from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

from .tool_tracker import reset_tool_usage_counter

# Read-only OpenShift commands that don't change cluster state
READ_ONLY_OC_COMMANDS = (
    "oc get",
    "oc describe",
    "oc logs",
    "oc status",
    "oc observe",
    "oc explain",
)


async def read_alert_diagnostics_data(ctx: Context) -> dict:
    """Read alert diagnostics from shared context."""
    state = await ctx.store.get("state")
    return {
        "namespace": state["namespace"],
        "alert_name": state["alert_name"],
        "alert_diagnostics": state["alert_diagnostics"],
        "alert_status": state["alert_status"],
        "recommendation": state["recommendation"],
    }


async def write_remediation_plan(
    ctx: Context, explanation: str, commands: list[str]
) -> str:
    """Write remediation plan to shared context for Host Orchestrator to execute."""

    if not commands:
        return "Commands can't be empty! Please use your tools and come up with remediation commands"

    # Reject read-only commands
    if any(cmd.startswith(READ_ONLY_OC_COMMANDS) for cmd in commands):
        return "Error: Read-only commands won't fix the issue. Use state-changing commands (oc set, oc scale, oc patch, etc.)"

    # Reset tool usage counter for the next invocation
    reset_tool_usage_counter()

    plan = {"explanation": explanation, "commands": commands}
    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"]["remediation_plan"] = plan
    return f"Stored remediation plan in context: {json.dumps(plan, indent=2)}. NOW YOU MUST HANDOFF TO 'Host Orchestrator' - this is MANDATORY."


# Tool definitions for LlamaIndex
context_tools = [
    FunctionTool.from_defaults(
        fn=read_alert_diagnostics_data,
        name="read_alert_diagnostics_data",
        description="""Read alert diagnostics from shared context.

        Purpose: Retrieve alert information to understand what needs to be remediated.

        Inputs: None - reads from context

        Returns: Dictionary with keys:
        - namespace (str): The namespace where the alert originated
        - alert_name (str): The name of the alert
        - alert_diagnostics (str): Diagnostic text describing the alert
        - alert_status (str): Current status of the alert
        - recommendation (str): Diagnose agent recommendations

        When to call: FIRST in Step 0 to understand the alert before investigation
        """,
    ),
    FunctionTool.from_defaults(
        fn=write_remediation_plan,
        name="write_remediation_plan",
        description="""Write remediation plan with VALID OC COMMANDS ONLY to shared context.

        Purpose: Create executable remediation commands and explanation for the Host Orchestrator to execute.

        Required Inputs:
        - explanation (str): Brief explanation of the issue and why the commands will fix it
          Example: "backend has 128Mi memory limit causing OOMKilled. Increasing to 512Mi."
        - commands (list[str]): List of EXECUTABLE oc commands (NOT descriptions)
          Must be valid shell commands that modify cluster state

        Returns: Confirmation that plan was stored with handoff instruction

        NEXT STEP AFTER THIS TOOL: You MUST immediately handoff to "Host Orchestrator"

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

        CRITICAL: After calling this tool, you MUST call handoff tool immediately in Step 4
        """,
    ),
]
