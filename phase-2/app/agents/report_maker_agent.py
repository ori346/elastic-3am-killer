import json
import os
from typing import Optional

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
from llama_index.llms.openai_like import OpenAILike

# LLM Configuration - Report Maker Agent specific environment variables with fallback to shared vars
API_BASE = os.getenv("REPORT_MAKER_AGENT_API_BASE", os.getenv("API_BASE"))
API_KEY = os.getenv("REPORT_MAKER_AGENT_API_KEY", os.getenv("API_KEY"))
MODEL = os.getenv("REPORT_MAKER_AGENT_MODEL", os.getenv("MODEL"))

llm = OpenAILike(
    api_base=API_BASE,
    api_key=API_KEY,
    model=MODEL,
    is_chat_model=True,
    max_tokens=2048,
    temperature=0.7,
    default_headers={"Content-Type": "application/json"},
)

# Cache for context document to avoid rebuilding on every query
_context_cache: Optional[str] = None


async def _get_or_build_context_doc(ctx: Context) -> str:
    """Get cached context document or build it if not cached."""
    global _context_cache

    if _context_cache is not None:
        return _context_cache

    state = await ctx.store.get("state")

    # Build comprehensive context document
    _context_cache = f"""
CONTEXT DATA:

Alert Name: {state.get('alert_name', 'N/A')}
Namespace: {state.get('namespace', 'N/A')}

Alert Diagnostics:
{json.dumps(state.get('alert_diagnostics', {}), indent=2)}

Remediation Plan:
{json.dumps(state.get('remediation_plan', {}), indent=2)}

Commands Execution Results:
{json.dumps(state.get('commands_execution_results', []), indent=2)}

Execution Success: {state.get('execution_success', False)}

Alert Status (Post-Remediation):
{json.dumps(state.get('alert_status', {}), indent=2)}
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
            - "What is the current status - resolved or unresolved?"

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


async def get_context_field(ctx: Context, field: str):
    """Get a specific field directly from context without LLM processing.

    Use this for fields that don't need interpretation - just return the value
    directly from context. This is more efficient than query_context for
    simple data retrieval.

    Args:
        field: The exact context field name to retrieve. Available fields:
            - "commands_execution_results": List of executed commands and their results
            - "execution_success": Boolean indicating if execution succeeded
            - "alert_status": Post-remediation alert state
            - "alert_diagnostics": Original alert information
            - "remediation_plan": The remediation plan object
            - "alert_name": Name of the alert
            - "namespace": Kubernetes namespace

    Returns:
        The field value (can be dict, list, str, bool, etc.)
    """
    state = await ctx.store.get("state")
    value = state.get(field, f"Field '{field}' not found in context")

    # Return the raw value so it can be used directly in the report dict
    return value


async def write_report_to_context(ctx: Context, report: dict) -> str:
    """Write the generated report to shared context.

    The report MUST be a dictionary with these exact fields:
    - "summary" (str): Brief summary of incident and remediation (2-3 sentences)
    - "root_cause" (str): Root cause analysis of the issue
    - "commands_executed" (list): List of [command, status] pairs
    - "remediation_steps" (str): Description of steps taken
    - "recommendations" (str): Recommendations to prevent recurrence
    - "status" (str): "Resolved" or "Unresolved"

    Args:
        report: Dictionary with the exact fields specified above

    Returns:
        Confirmation message and handoff instruction
    """
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
        - "What is the status - resolved or unresolved?"

        The tool uses LLM to interpret your question and generate an answer.
        Context is cached, so multiple queries are efficient.
        """,
    ),
    FunctionTool.from_defaults(
        fn=get_context_field,
        name="get_context_field",
        description="""Get a specific field directly from context.

        Use this for simple data that doesn't need interpretation:
        - "commands_execution_results" - get command execution results
        - "execution_success" - check if execution succeeded
        - "alert_status" - get post-remediation alert state

        This is faster than query_context for direct field access.
        """,
    ),
    FunctionTool.from_defaults(
        fn=write_report_to_context,
        name="write_report_to_context",
        description="""Write the final report to context.

        Report MUST have these exact fields:
        - summary (str): 2-3 sentence summary
        - root_cause (str): Root cause analysis
        - commands_executed (list): [command, status] pairs
        - remediation_steps (str): Steps taken
        - recommendations (str): Prevention recommendations
        - status (str): "Resolved" or "Unresolved"

        After calling this, MUST handoff to 'Host Orchestrator'.
        """,
    ),
]

system_prompt = """You are a report generation specialist with intelligent context querying.

YOUR TASK:
Generate a remediation report with these EXACT fields:
- summary: Brief summary (2-3 sentences) of incident and remediation
- root_cause: Root cause of the issue
- commands_executed: List of [command, status] pairs from execution
- remediation_steps: Description of remediation steps taken
- recommendations: Recommendations to prevent recurrence
- status: "Resolved" if execution succeeded and alert cleared, else "Unresolved"

TWO TYPES OF TOOLS:

1. query_context - For fields needing ANALYSIS/SYNTHESIS:
   Use natural language queries to get interpreted information:
   - summary: query_context("Provide a 2-3 sentence summary of the incident and how it was remediated")
   - root_cause: query_context("What was the root cause of this issue?")
   - remediation_steps: query_context("What steps were taken to remediate the problem?")
   - recommendations: query_context("What recommendations would prevent this issue from recurring?")
   - status: query_context("Based on execution success and alert status, is this resolved or unresolved?")

2. get_context_field - For DIRECT field access (no interpretation needed):
   Use for simple data retrieval:
   - commands_executed: get_context_field("commands_execution_results")

MANDATORY WORKFLOW:
1. Use query_context for fields needing analysis (summary, root_cause, etc.)
2. Use get_context_field for direct data (commands_executed)
3. Build the report dict with ALL required fields
4. Call write_report_to_context with the complete report
5. IMMEDIATELY handoff to "Host Orchestrator"

EXAMPLE WORKFLOW:
1. query_context("Provide a 2-3 sentence summary...") → get summary
2. query_context("What was the root cause?") → get root_cause
3. get_context_field("commands_execution_results") → get commands_executed
4. query_context("What steps were taken?") → get remediation_steps
5. query_context("What recommendations...") → get recommendations
6. query_context("Is this resolved or unresolved?") → get status
7. write_report_to_context(report={all fields}) → store report
8. handoff(to_agent="Host Orchestrator", reason="Report completed")

CRITICAL RULES:
- Report MUST have all 6 fields with exact names
- Use query_context for interpreted fields
- Use get_context_field for direct field access
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
