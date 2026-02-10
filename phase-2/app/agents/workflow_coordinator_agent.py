import shlex
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
    commands = state.remediation_plan["commands"]

    if not commands:
        return "Commands are not found. Either the Alert Remediation Specialist failed or it needs to be called"

    results = []
    all_succeeded = True

    for cmd in commands:
        returncode = subprocess.run(
            shlex.split(cmd), capture_output=False, timeout=TIMEOUTS.command_execution
        ).returncode
        status = "Success" if returncode == 0 else "Failed"
        if returncode != 0:
            all_succeeded = False
        results.append([cmd, status])

    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"].commands_execution_results = results
        ctx_state["state"].execution_success = all_succeeded

    return f"Executed {len(results)} commands. Success: {all_succeeded}. Results: {results}. Now proceed to Step 3: HANDOFF TO 'Incident Report Generator' - this is MANDATORY."


system_prompt = """Remediation workflow orchestrator. Execute steps 1-3 IN ORDER. DO NOT skip ahead.

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
- Start directly with Step 1 (context is already populated from JSON input)
- Always proceed to Step 3 after Step 2 (regardless of execution success/failure)

HANDOFF CONTEXT REQUIREMENTS:
- ALWAYS include specific alert information from stored context in handoff reasons
- You have access to stored context data: diagnosis_request with incident_id, namespace, alert info, diagnostics_suggestions
- For Step 1: Build reason like: "Investigate [alert.name] alert in namespace '[namespace]'. Issue: [brief description from diagnostics_suggestions]. Analyze cluster state and create remediation commands."
- For Step 3: Build reason like: "Generate report for [alert_name] alert in namespace '[namespace]'. Executed [X] commands with [SUCCESS/FAILED] outcome. Commands attempted: [brief summary]. Create comprehensive incident report."
- Use handoff(to_agent="Agent Name", reason="Your crafted detailed context here...")
- NEVER use generic reasons like "analyze alert" or "generate report"
- Read from context to understand what happened and craft specific, informative handoff messages
- Each handoff should tell the receiving agent exactly what to focus on based on the specific situation"""


tools = [
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
