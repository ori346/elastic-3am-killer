import logging
import os
import subprocess
from asyncio import sleep

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
from llama_index.llms.openai_like import OpenAILike

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# LLM Configuration - Host Agent specific environment variables with fallback to shared vars
API_BASE = os.getenv("HOST_AGENT_API_BASE", os.getenv("API_BASE"))
API_KEY = os.getenv("HOST_AGENT_API_KEY", os.getenv("API_KEY"))
MODEL = os.getenv("HOST_AGENT_MODEL", os.getenv("MODEL"))

llm = OpenAILike(
    api_base=API_BASE,
    api_key=API_KEY,
    model=MODEL,
    is_chat_model=True,
    max_tokens=1024,
    temperature=0.4,
    default_headers={"Content-Type": "application/json"},
    system_prompt=(
        "You are helping the AI Orchestrator Agent to remediate alerts in OpenShift cluster. "
        "The agent is not allowed to execute commands that do not modify the cluster state such as get, describe, status, logs, etc. "
        "The agent's role is only orchestrating the workflow and not investigating by itself. The agent uses other agents for investigation."
    ),
)


async def execute_commands(ctx: Context) -> str:
    """Execute commands from remediation plan. Returns: [[cmd, "Success"/"Failed"], ...]"""
    state = await ctx.store.get("state")
    commands = state["remediation_plan"]["commands"]

    if not commands:
        return "Commands are not found. Either the remediation agent failed or it needs to be called"

    results = []
    all_succeeded = True

    for cmd in commands:
        if cmd.startswith(
            ("oc get", "oc describe", "oc logs", "oc status", "oc observe")
        ):
            async with ctx.store.edit_state() as ctx_state:
                ctx_state["state"]["commands_execution_results"] = []
                ctx_state["state"]["execution_success"] = False
            return "Error: Read-only commands are not allowed for remediation. Try to use the Remediation Agent to investigate the issue."

        returncode = subprocess.run(
            cmd.split(), capture_output=False, timeout=60
        ).returncode
        status = "Success" if returncode == 0 else "Failed"
        if returncode != 0:
            all_succeeded = False
        results.append([cmd, status])

    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"]["commands_execution_results"] = results
        ctx_state["state"]["execution_success"] = all_succeeded

    if all_succeeded:
        return f"Executed {len(results)} commands. Success: {all_succeeded}. Results: {results}. Now proceed to Step 3 (check_alert_status)."
    else:
        return f"Executed {len(results)} commands. Success: {all_succeeded}. Results: {results}. EXECUTION FAILED - SKIP Step 3 and go directly to Step 4: HANDOFF TO 'Remediation Report Generator' - this is MANDATORY."


async def check_alert_status(ctx: Context) -> str:
    """Check if alerts are still firing using Alertmanager."""
    state = await ctx.store.get("state")

    if not state["commands_execution_results"]:
        return "There are no commands executed, alerts won't be resolved. Try to execute the commands or call the remediation agent before checking alert status."

    alert_name = state["alert_name"]

    if not alert_name:
        return "The alert name is not set in context, set it first"

    try:
        await sleep(30)  # Give Alertmanager time to update
        result = subprocess.run(
            [
                "oc",
                "-n",
                "openshift-monitoring",
                "exec",
                "alertmanager-main-0",
                "--",
                "amtool",
                "alert",
                "query",
                f"alertname={alert_name}",
                "--alertmanager.url=http://localhost:9093",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        alert_status = (
            result.stdout
            if result.returncode == 0
            else f"Failed to check alerts: {result.stderr}"
        )
        async with ctx.store.edit_state() as ctx_state:
            ctx_state["state"]["alert_status"] = alert_status
        return f"Alert status stored: {alert_status}. NOW YOU MUST HANDOFF TO 'Remediation Report Generator' - this is MANDATORY."
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        async with ctx.store.edit_state() as ctx_state:
            ctx_state["state"]["alert_status"] = error_msg
        return f"{error_msg}. NOW YOU MUST HANDOFF TO 'Remediation Report Generator' - this is MANDATORY."


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
        recommendation: Recommended remediation actions for the remediation agent
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

    return f"Stored {len(stored_keys)} fields in context: {', '.join(stored_keys)}. NOW YOU MUST HANDOFF TO 'Remediation Agent' - this is MANDATORY."


system_prompt = """Remediation workflow orchestrator. Execute steps 0-4 IN ORDER. DO NOT skip ahead.

STEP 0: Call store_alert_info FIRST
- Input: alert_name (str), namespace (str), alert_diagnostics (str), recommendation (str).
- Output: Confirmation stored in context
- The tool will tell you to handoff to Remediation Agent next

STEP 1: Handoff to Remediation Agent for investigation and planning
- MANDATORY: Use handoff tool with to_agent="Remediation Agent"
- The Remediation Agent will:
  * Read alert diagnostics from context
  * Analyze the issue
  * Create a remediation plan with commands
  * Store the plan in context
  * Handoff back to you
- WAIT - do nothing until agent hands back

STEP 2: Execute commands (ONLY after Remediation Agent hands back)
- Call execute_commands (reads command list from context automatically)
- Check the execute_commands result:
  * If result contains "Success: True" → proceed to Step 3
  * If result contains "Success: False" or "Error" → SKIP Step 3, go directly to Step 4

STEP 3: Check alert (ONLY if Step 2 succeeded)
- Call check_alert_status to verify if alert is still firing
- This stores the alert status in context for the report
- The tool will tell you to send report and STOP next
- If you skipped this step due to failed execution, that's OK - proceed to Step 4

STEP 4: Handoff to Report Generator to create remediation report
- MANDATORY: Use handoff tool with to_agent="Remediation Report Generator"
- Reason: "Generate remediation report from context data"
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
- Step 1 handoff to Remediation Agent is MANDATORY - don't skip it
- Step 4 handoff to Report Generator is MANDATORY - don't skip it
- If you already did Step 0, proceed to Step 1 (don't repeat Step 0)
- If Step 2 execution fails, SKIP Step 3 and go directly to Step 4"""


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
        - recommendation (str): Recommended remediation actions for the remediation agent

        Returns: Confirmation message with list of fields stored in context

        When to call: FIRST in Step 0, before any other operations
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_commands,
        name="execute_commands",
        description="""Execute OpenShift remediation commands from the remediation plan.

        Purpose: Execute the oc commands that were prepared by the Remediation Agent to fix the issue.

        Inputs: None - reads commands from context["remediation_plan"]["commands"]

        Pre-requisites:
        - Remediation Agent must have completed and stored commands in context
        - Commands must be stored in context under key "remediation_plan"

        Returns: Execution results as [[command, status], ...] and overall success/failure
        - If Success: True → tells you to proceed to Step 3 (check_alert_status)
        - If Success: False → tells you to SKIP Step 3 and HANDOFF to Report Generator

        When to call: In Step 2, ONLY after Remediation Agent hands back control

        Next step after this tool:
        - If execution succeeded: proceed to Step 3
        - If execution failed: go directly to Step 4 (handoff to Report Generator)
        """,
    ),
    FunctionTool.from_defaults(
        fn=check_alert_status,
        name="check_alert_status",
        description="""Check if the alert is still firing in Alertmanager after remediation.

        Purpose: Verify that the remediation actions resolved the alert.

        Inputs: None - reads alert_name from context["alert_name"]

        Pre-requisites:
        - Alert name must be stored in context
        - Commands must have been executed (execute_commands called)

        Returns: Alert status from Alertmanager or error message
        - ALWAYS ends with: "NOW YOU MUST HANDOFF TO 'Remediation Report Generator'"

        Behavior:
        - Waits for Alertmanager to update
        - Queries Alertmanager for the specific alert by name
        - Stores result in context["alert_status"]

        When to call: In Step 3, ONLY if Step 2 (execute_commands) succeeded

        CRITICAL: After this tool returns, you MUST immediately handoff to 'Remediation Report Generator'
        """,
    ),
]


agent = ReActAgent(
    name="Host Orchestrator",
    description="Orchestrates remediation workflow and makes execution decisions",
    tools=tools,
    llm=llm,
    system_prompt=system_prompt,
    can_handoff_to=["Remediation Agent", "Remediation Report Generator"],
)
