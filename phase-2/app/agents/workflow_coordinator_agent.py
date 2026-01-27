import subprocess

from configs import TIMEOUTS, WORKFLOW_COORDINATOR_LLM, create_workflow_coordinator_llm
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

# LLM Configuration - using shared configuration
llm = create_workflow_coordinator_llm(
    max_tokens=WORKFLOW_COORDINATOR_LLM.max_tokens,
    temperature=WORKFLOW_COORDINATOR_LLM.temperature,
)


async def execute_commands(ctx: Context) -> str:
    """Execute commands from remediation plan. Returns: [[cmd, "Success"/"Failed"], ...]"""
    state = await ctx.store.get("state")
    commands = state["remediation_plan"]["commands"]

    if not commands:
        return "Commands are not found. Either the Alert Remediation Specialist failed or it needs to be called"

    results = []
    all_succeeded = True

    for cmd in commands:
        returncode = subprocess.run(
            cmd.split(), capture_output=False, timeout=TIMEOUTS.command_execution
        ).returncode
        status = "Success" if returncode == 0 else "Failed"
        if returncode != 0:
            all_succeeded = False
        results.append([cmd, status])

    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"]["commands_execution_results"] = results
        ctx_state["state"]["execution_success"] = all_succeeded

    return f"Executed {len(results)} commands. Success: {all_succeeded}. Results: {results}. Now proceed to Step 3: HANDOFF TO 'Incident Report Generator' - this is MANDATORY."


async def store_alert_info(
    ctx: Context,
    alert_name: str,
    namespace: str,
    alert_diagnostics: str,
    recommendation: str,
) -> str:
    """Store alert information in context for other agents to access.

    Args:
        alert_name: The name of the alert
        namespace: The namespace where the alert originated
        alert_diagnostics: The alert diagnostic text
        recommendation: Recommended remediation actions for the Alert Remediation Specialist
    """
    # Collect all parameters into a dictionary
    alert_data = {
        "alert_name": alert_name,
        "namespace": namespace,
        "alert_diagnostics": alert_diagnostics,
        "recommendation": recommendation,
    }

    async with ctx.store.edit_state() as ctx_state:
        # Store each field into the context
        for key, value in alert_data.items():
            ctx_state["state"][key] = value

    stored_keys = list(alert_data.keys())

    return f"Stored {len(stored_keys)} fields in context: {', '.join(stored_keys)}. NOW YOU MUST HANDOFF TO 'Alert Remediation Specialist' with detailed context - this is MANDATORY."


system_prompt = """Remediation workflow orchestrator. Execute steps 0-3 IN ORDER. DO NOT skip ahead.

STEP 0: Call store_alert_info FIRST
- Input: alert_name (str), namespace (str), alert_diagnostics (str), recommendation (str).
- Output: Confirmation stored in context
- The tool will tell you to handoff to Alert Remediation Specialist next

STEP 1: Handoff to Alert Remediation Specialist for investigation and planning
- MANDATORY: Use handoff tool with to_agent="Alert Remediation Specialist"
- MANDATORY: Include a detailed reason with specific context:
  * Alert name and namespace from context
  * Brief description of the issue
  * What the agent should focus on
  * Example reason: "Investigate HighMemoryUsage alert in namespace 'app-prod'. Alert indicates memory consumption above 80% threshold. Analyze pod resources, check for memory leaks, and create remediation commands to address resource constraints."
- The Alert Remediation Specialist will:
  * Read alert diagnostics from context
  * Analyze the issue
  * Create a remediation plan with commands
  * Store the plan in context
  * Handoff back to you
- WAIT - do nothing until agent hands back

STEP 2: Execute commands (ONLY after Alert Remediation Specialist hands back)
- Call execute_commands (reads command list from context automatically)
- Always proceed to Step 3 after command execution (regardless of success/failure)

STEP 3: Handoff to Report Generator to create remediation report
- MANDATORY: Use handoff tool with to_agent="Incident Report Generator"
- MANDATORY: Include a detailed reason with execution context:
  * Alert name and outcome (success/failure)
  * Number of commands executed
  * Brief summary of what was attempted
  * Example reason: "Generate remediation report for HighMemoryUsage alert in namespace 'app-prod'. Executed 3 remediation commands with SUCCESS/FAILED status. Commands included resource limit adjustments and pod scaling. Create comprehensive incident report with root cause analysis and prevention recommendations."
- The Report Generator will:
  * Use query_context to ask questions about the incident (summary, root cause, etc.)
  * Use get_context_field to retrieve execution results
  * Create a structured report with all required fields
  * Store the report in context["report"]
  * Handoff back to you
- WAIT for handoff back - Then say "Workflow completed successfully" and Stop

CRITICAL RULES:
- Do steps IN ORDER - complete step N before starting step N+1
- After EVERY handoff, WAIT for agent to return before proceeding
- Step 1 handoff to Alert Remediation Specialist is MANDATORY - don't skip it
- Step 3 handoff to Report Generator is MANDATORY - don't skip it
- If you already did Step 0, proceed to Step 1 (don't repeat Step 0)
- Always proceed to Step 3 after Step 2 (regardless of execution success/failure)

HANDOFF CONTEXT REQUIREMENTS:
- ALWAYS include specific alert information from stored context in handoff reasons
- You have access to stored context data: alert_name, namespace, alert_diagnostics, recommendation
- For Step 1: Build reason like: "Investigate [alert_name] alert in namespace '[namespace]'. Issue: [brief description from alert_diagnostics]. Focus on: [key areas from recommendation]. Analyze cluster state and create remediation commands."
- For Step 3: Build reason like: "Generate report for [alert_name] alert in namespace '[namespace]'. Executed [X] commands with [SUCCESS/FAILED] outcome. Commands attempted: [brief summary]. Create comprehensive incident report."
- Use handoff(to_agent="Agent Name", reason="Your crafted detailed context here...")
- NEVER use generic reasons like "analyze alert" or "generate report"
- Read from context to understand what happened and craft specific, informative handoff messages
- Each handoff should tell the receiving agent exactly what to focus on based on the specific situation"""


tools = [
    FunctionTool.from_defaults(
        fn=store_alert_info,
        name="store_alert_info",
        description="""Store alert information in shared context for other agents to access.

        Purpose: Initialize the remediation workflow by storing alert information.

        Required Inputs:
        - alert_name (str): The name of the alert from the monitoring system (e.g., "HighMemoryUsage")
        - namespace (str): The OpenShift namespace where the alert originated (e.g., "integration-test-ofridman")
        - alert_diagnostics (str): The diagnostic text describing the alert details and context
        - recommendation (str): Recommended remediation actions for the Alert Remediation Specialist

        Returns: Confirmation message with list of fields stored in context

        When to call: FIRST in Step 0, before any other operations
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_commands,
        name="execute_commands",
        description="""Execute OpenShift remediation commands from the remediation plan.

        Purpose: Execute the oc commands that were prepared by the Alert Remediation Specialist to fix the issue.

        Inputs: None - reads commands from context["remediation_plan"]["commands"]

        Pre-requisites:
        - Alert Remediation Specialist must have completed and stored commands in context
        - Commands must be stored in context under key "remediation_plan"

        Returns: Execution results as [[command, status], ...] and overall success/failure
        - Always tells you to proceed to Step 3 (handoff to Report Generator)

        When to call: In Step 2, ONLY after Alert Remediation Specialist hands back control

        Next step after this tool:
        - Always proceed to Step 3 (handoff to Report Generator)
        """,
    ),
]


agent = ReActAgent(
    name="Workflow Coordinator",
    description="Orchestrates remediation workflow and makes execution decisions",
    tools=tools,
    llm=llm,
    system_prompt=system_prompt,
    can_handoff_to=["Alert Remediation Specialist", "Incident Report Generator"],
)
