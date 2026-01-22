import json
from typing import Optional

from configs import REPORT_MAKER_AGENT_LLM, create_report_maker_agent_llm
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

# LLM Configuration - using shared configuration
llm = create_report_maker_agent_llm(
    max_tokens=REPORT_MAKER_AGENT_LLM.max_tokens,
    temperature=REPORT_MAKER_AGENT_LLM.temperature,
)

# Cache for context document to avoid rebuilding on every query
_context_cache: Optional[str] = None


async def _get_or_build_context_doc(ctx: Context) -> str:
    """Get cached context document or build it if not cached."""
    global _context_cache

    if _context_cache is not None:
        return _context_cache

    state = await ctx.store.get("state")

    # Build comprehensive context document with compact JSON to minimize token usage
    _context_cache = f"""
CONTEXT DATA:

Alert Name: {state["alert_name"]}
Namespace: {state["namespace"]}

Alert Diagnostics:
{state["alert_diagnostics"]}

Remediation Plan:
{json.dumps(state['remediation_plan'], separators=(',', ':'))}

Commands Execution Results:
{state['commands_execution_results']}

Execution Success: {state['execution_success']}

Alert Status (Post-Remediation):
{state['alert_status']}
"""
    return _context_cache


async def query_context(ctx: Context, query: str) -> str:
    """Query the context using natural language.

    Ask questions about the remediation context in natural language and get
    relevant answers. Use this for fields that require analysis, interpretation,
    or synthesis of the context data.

    Args:
        query: Natural language question about the context. Examples:
            - "What was the root cause of the issue?"
            - "Provide a 2-3 sentence summary of the incident and remediation"
            - "What steps were taken to remediate the problem?"
            - "What recommendations would prevent this from happening again?"
            - "What is the current alert status - active or inactive?"

    Returns:
        Answer to your query based on the context data
    """
    context_doc = await _get_or_build_context_doc(ctx)

    # Use the LLM to answer the query based on context
    query_prompt = f"""You are a context query assistant. Answer the following question based ONLY on the provided context data.

Context:
{context_doc}

Question: {query}

Provide a direct, concise answer based on the context. If the information is not in the context, say "Information not available in context."
Answer:"""

    try:
        response = llm.complete(query_prompt)
        return str(response)
    except Exception as e:
        return f"Error querying context: {str(e)}"


def _validate_report_fields(
    summary: str, root_cause: str, remediation_steps: str, recommendations: str
) -> Optional[str]:
    """Validate that all required report fields are provided.

    Returns:
        Error message if validation fails, None if all fields are valid
    """
    missing_fields = []
    if not summary or summary is None:
        missing_fields.append("summary")
    if not root_cause or root_cause is None:
        missing_fields.append("root_cause")
    if not remediation_steps or remediation_steps is None:
        missing_fields.append("remediation_steps")
    if not recommendations or recommendations is None:
        missing_fields.append("recommendations")

    if missing_fields:
        return f"Error: Missing required fields: {', '.join(missing_fields)}. Please use query_context to get all required fields before calling write_report_to_context."

    return None


async def write_report_to_context(
    ctx: Context,
    summary: str,
    root_cause: str,
    remediation_steps: str,
    recommendations: str,
) -> str:
    """Write the generated report to shared context.

    This function builds a complete report by combining the provided fields
    with data extracted directly from context (commands_execution_results and alert_status).

    Args:
        summary: Brief summary of incident and remediation (2-3 sentences)
        root_cause: Root cause analysis of the issue
        remediation_steps: Description of steps taken
        recommendations: Recommendations to prevent recurrence

    Returns:
        Confirmation message and handoff instruction
    """
    # Validate all required fields are provided
    validation_error = _validate_report_fields(
        summary, root_cause, remediation_steps, recommendations
    )
    if validation_error:
        return validation_error

    # Extract fields from context
    state = await ctx.store.get("state")
    commands_executed = state["commands_execution_results"]
    alert_status = state["alert_status"]

    # Build complete report
    report = {
        "summary": summary,
        "root_cause": root_cause,
        "commands_executed": commands_executed,
        "remediation_steps": remediation_steps,
        "recommendations": recommendations,
        "alert_status": alert_status,
    }

    # Store report in context
    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"]["report"] = report

    return f"Report stored successfully: {json.dumps(report, indent=2)}. YOU MUST NOW HANDOFF TO 'Host Orchestrator'."


tools = [
    FunctionTool.from_defaults(
        fn=query_context,
        name="query_context",
        description="""Query the remediation context using natural language questions.

        Use this for fields that need analysis or synthesis:
        - "What was the root cause?"
        - "Provide a summary of the incident"
        - "What recommendations would prevent this?"
        - "What steps were taken to remediate the problem?"

        The tool uses LLM to interpret your question and generate an answer.
        Context is cached, so multiple queries are efficient.
        """,
    ),
    FunctionTool.from_defaults(
        fn=write_report_to_context,
        name="write_report_to_context",
        description="""Write the final report to context.

        This function takes 4 string parameters and automatically extracts
        commands_executed and alert_status from context to build the complete report.

        MANDATORY parameters:
        - summary (str): 2-3 sentence summary of incident and remediation
        - root_cause (str): Root cause analysis
        - remediation_steps (str): Description of steps taken
        - recommendations (str): Prevention recommendations

        After calling this, MUST handoff to 'Host Orchestrator'.
        """,
    ),
]

system_prompt = """You are a report generation specialist with intelligent context querying.

YOUR TASK:
Generate a remediation report by gathering information from context and calling write_report_to_context.

The final report will automatically include these fields:
- summary: Brief summary (2-3 sentences) of incident and remediation
- root_cause: Root cause of the issue
- commands_executed: List of [command, status] pairs (automatically extracted from context)
- remediation_steps: Description of remediation steps taken
- recommendations: Recommendations to prevent recurrence
- alert_status: "Active" or "Inactive" (automatically extracted from context)

YOUR TOOLS:

1. query_context - For fields needing ANALYSIS/SYNTHESIS:
   Use natural language queries to get interpreted information:
   - summary: query_context("Provide a 2-3 sentence summary of the incident and how it was remediated")
   - root_cause: query_context("What was the root cause of this issue?")
   - remediation_steps: query_context("What steps were taken to remediate the problem?")
   - recommendations: query_context("What recommendations would prevent this issue from recurring?")

2. write_report_to_context - Store the report:
   Takes 4 parameters: summary, root_cause, remediation_steps, recommendations
   Automatically extracts commands_executed and alert_status from context

MANDATORY WORKFLOW:
1. Use query_context to get summary
2. Use query_context to get root_cause
3. Use query_context to get remediation_steps
4. Use query_context to get recommendations
5. Call write_report_to_context with the 4 fields (commands_executed and alert_status are auto-extracted)
6. IMMEDIATELY handoff to "Host Orchestrator"

EXAMPLE WORKFLOW:
1. query_context("Provide a 2-3 sentence summary...") → get summary
2. query_context("What was the root cause?") → get root_cause
3. query_context("What steps were taken?") → get remediation_steps
4. query_context("What recommendations...") → get recommendations
5. write_report_to_context(summary, root_cause, remediation_steps, recommendations) → stores complete report
6. handoff(to_agent="Host Orchestrator", reason="Report completed")

CRITICAL RULES:
- Use query_context to get the 4 interpreted fields
- Call write_report_to_context with exactly 4 string parameters
- ALWAYS handoff after write_report_to_context
- DO NOT answer with text - only use tools"""

agent = ReActAgent(
    name="Remediation Report Generator",
    description="Generates structured remediation reports using intelligent context queries",
    tools=tools,
    llm=llm,
    system_prompt=system_prompt,
    can_handoff_to=["Host Orchestrator"],
)
