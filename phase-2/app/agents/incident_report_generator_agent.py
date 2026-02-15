import logging
from typing import Optional

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

from configs import INCIDENT_REPORT_GENERATOR_LLM, create_incident_report_generator_llm

from .models import AgentReport, Report

logger = logging.getLogger(__name__)
# LLM Configuration - using shared configuration
llm = create_incident_report_generator_llm(
    max_tokens=INCIDENT_REPORT_GENERATOR_LLM.max_tokens,
    temperature=INCIDENT_REPORT_GENERATOR_LLM.temperature,
)

# Cache for context document to avoid rebuilding on every query
_context_cache: Optional[str] = None


async def _get_or_build_context_doc(ctx: Context) -> str:
    """Get cached context document or build it if not cached."""
    global _context_cache

    if _context_cache is None:
        state = await ctx.store.get("state")
        _context_cache = state.model_dump_json(
            exclude_unset=True, exclude_none=True, indent=2
        )

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
    summary: str, diagnosis: str, recommendations: str
) -> Optional[str]:
    """Validate that all required report fields are provided.

    Returns:
        Error message if validation fails, None if all fields are valid
    """
    missing_fields = []
    if not summary or summary is None:
        missing_fields.append("summary")
    if not diagnosis or diagnosis is None:
        missing_fields.append("diagnosis")
    if not recommendations or recommendations is None:
        missing_fields.append("recommendations")

    if missing_fields:
        return f"Error: Missing required fields: {', '.join(missing_fields)}. Please use query_context to get all required fields before calling write_report_to_context."

    return None


async def write_report_to_context(
    ctx: Context,
    summary: str,
    diagnosis: str,
    recommendations: str,
) -> str:
    """Write the generated report to shared context.

    This function builds a complete report by combining the provided fields
    with data extracted directly from context (commands_execution_results).

    Args:
        summary: Brief summary of incident and remediation (2-3 sentences)
        diagnosis: Root cause analysis of the issue
        recommendations: Recommendations to prevent recurrence

    Returns:
        Confirmation message and handoff instruction
    """
    # Validate all required fields are provided
    validation_error = _validate_report_fields(summary, diagnosis, recommendations)

    if validation_error:
        return validation_error

    # Extract fields from context
    state = await ctx.store.get("state")
    commands_executed = state.commands_execution_results

    # Build complete report
    report = Report(
        incident_id=state.request.incident_id,
        diagnosis=diagnosis,
        summary=summary,
        recommendations=recommendations,
        commands_executed=commands_executed,
    )

    # Store report in context
    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"].report = report

    logger.info(f"Report written to context: {report.model_dump_json(indent=2)}")
    return "Report stored successfully. YOU MUST NOW HANDOFF TO 'Workflow Coordinator'."


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

        This function takes 3 string parameters and automatically extracts
        commands_executed from context to build the complete report.

        MANDATORY parameters:
        - summary (str): 2-3 sentence summary of incident and remediation
        - diagnosis (str): Root cause analysis
        - recommendations (str): Prevention recommendations

        After calling this, MUST handoff to 'Workflow Coordinator'.
        """,
    ),
]

system_prompt = f"""You are a report generation specialist with intelligent context querying.

YOUR TASK:
Generate a remediation report by gathering information from context and calling write_report_to_context.

The final report MUST include these fields:
{AgentReport.model_fields}

YOUR TOOLS:

1. query_context - For fields needing ANALYSIS/SYNTHESIS:
   Use natural language queries to get interpreted information:
   - summary: query_context("Provide a 2-3 sentence summary of the incident and how it was remediated")
   - diagnosis: query_context("What was the root cause of this issue?")
   - recommendations: query_context("What recommendations would prevent this issue from recurring? or What should be investigated further?")

2. write_report_to_context - Store the report:
   Takes 3 parameters: summary, diagnosis, recommendations
   Automatically extracts commands_executed from context

MANDATORY WORKFLOW:
1. Use query_context to get summary
2. Use query_context to get diagnosis
3. Use query_context to get recommendations
4. Call write_report_to_context with the 3 fields (commands_executed is auto-extracted)
5. IMMEDIATELY handoff to "Workflow Coordinator"

EXAMPLE WORKFLOW:
1. query_context("Provide a 2-3 sentence summary...") → get summary
2. query_context("What was the root cause of this issue?") → get diagnosis
3. query_context("What recommendations...") → get recommendations
4. write_report_to_context(summary, diagnosis, recommendations) → stores complete report
5. handoff(to_agent="Workflow Coordinator", reason="Report completed")

CRITICAL RULES:
- Use query_context to get the 3 interpreted fields
- Call write_report_to_context with exactly 3 string parameters
- ALWAYS handoff after write_report_to_context
- DO NOT answer with text - only use tools"""

agent = ReActAgent(
    name="Incident Report Generator",
    description="Generates structured remediation reports using intelligent context queries",
    tools=tools,
    llm=llm,
    system_prompt=system_prompt,
    can_handoff_to=["Workflow Coordinator"],
    early_stopping_method='generate'
)
