"""
Workflow Agent Executor

Orchestrates alert_remediation_specialist and incident_report_generator to handle alert diagnosis,
command execution decisions, and report generation.
"""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import DataPart, Message, TextPart
from llama_index.core.agent.workflow import (
    AgentOutput,
    AgentWorkflow,
    ToolCall,
    ToolCallResult,
)
from llama_index.core.workflow import Context

from configs import WORKFLOW

from .alert_remediation_specialist_agent import agent as alert_remediation_specialist
from .incident_report_generator_agent import agent as report_generator_agent
from .models import RemediationRequest, Report, WorkflowState
from .workflow_coordinator_agent import agent as workflow_coordinator

logger = logging.getLogger(__name__)


class WorkflowAgentExecutor(AgentExecutor):
    """A dummy agent that starts the ReAct agents."""

    def _extract_remediation_request_from_message(
        self, message: Message
    ) -> RemediationRequest:
        if not message or not message.parts:
            return "No diagnostics provided"

        for part in message.parts:
            if isinstance(part.root, TextPart):
                return RemediationRequest.model_validate_strings(part.root.text)
            elif isinstance(part.root, DataPart):
                return RemediationRequest.model_validate(part.root.data)

    # TODO add case where we have a remediation report from a previous execution and we want to continue the remediation process and update the report accordingly - this will be the retry case, we need to make sure that the workflow can handle this case and continue from where it left off instead of starting from scratch
    async def _generate_execution_prompt(self, retry_count: int) -> str:
        """Generate appropriate prompt based on whether this is a retry or initial execution."""
        if retry_count > 0:
            return "You failed to generate a report. Please continue from where you stopped, complete the alert remediation and the report generation."
        else:
            return "It's 3am and you recived alert in OpenShift cluster. Follow your instructions and complete the remdiation workflow."

    async def _execute_workflow_with_streaming(
        self, prompt: str, ctx: Context, agent: AgentWorkflow
    ) -> WorkflowState:
        """Execute a single workflow attempt with event streaming and return final state.
        This method does not handle retries - it performs one execution attempt only."""
        logger.info("Running ReActAgent autonomous workflow...")

        handler = agent.run(prompt, ctx=ctx)

        current_agent = None
        async for event in handler.stream_events():
            current_agent = await self._process_workflow_event(event, current_agent)

        logger.info("Agent workflow completed autonomously")

        state: WorkflowState = await ctx.store.get("state")
        return state

    async def _process_workflow_event(self, event, current_agent: str) -> str:
        """Process individual workflow events and log appropriately."""
        if (
            hasattr(event, "current_agent_name")
            and event.current_agent_name != current_agent
        ):
            current_agent = event.current_agent_name
            logger.info(f"\n{'=' * 50}\n🤖 Agent: {current_agent}\n{'=' * 50}")

        elif isinstance(event, AgentOutput):
            if event.response.content:
                logger.info(f"📤 Output: {event.response.content}")
            if event.tool_calls:
                logger.debug(
                    f"🛠️  Planning to use tools: {[call.tool_name for call in event.tool_calls]}"
                )

        elif isinstance(event, ToolCallResult):
            logger.info(f"🔧 Tool Result ({event.tool_name}):")
            logger.info(f"  Arguments: {event.tool_kwargs}")
            logger.info(f"  Output: {event.tool_output}")

        elif isinstance(event, ToolCall):
            logger.info(f"🔨 Calling Tool: {event.tool_name}")
            logger.debug(f"  With arguments: {event.tool_kwargs}")

        return current_agent

    async def _handle_execution_success(
        self, report: Report, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Handle successful workflow completion by sending report and marking task complete."""
        response_message = updater.new_agent_message(
            parts=[DataPart(data=report.model_dump())]
        )
        await event_queue.enqueue_event(response_message)
        await updater.complete()
        logger.info("Task execution completed successfully")

    async def _handle_retry_exhaustion(
        self, retry_count: int, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Handle failure after exhausting all retry attempts."""
        logger.error(
            f"Report generation failed after {retry_count + 1} attempts, exceeding max_retries ({WORKFLOW.max_retries})"
        )

        error_message = updater.new_agent_message(
            parts=[
                TextPart(
                    text="# Remediation process failed\n The workflow was unable to complete the report generation. Please continue from where you stop and finsish the remediation process."
                )
            ]
        )
        await event_queue.enqueue_event(error_message)
        await updater.failed()

    async def _handle_execution_exception(
        self, exception: Exception, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Handle unexpected exceptions during orchestration."""
        logger.error(f"Error during orchestration: {str(exception)}", exc_info=True)

        error_message = updater.new_agent_message(
            parts=[TextPart(text=f"# Orchestration Error\n\n{str(exception)}")]
        )
        await event_queue.enqueue_event(error_message)
        await updater.failed()
        logger.info("Task marked as failed")

    async def _execute_with_retry_tracking(
        self,
        event_queue: EventQueue,
        updater: TaskUpdater,
        ctx: Context,
        agent: AgentWorkflow,
    ) -> None:
        """Execute workflow with iterative retry tracking."""
        current_retry = 0

        while current_retry <= WORKFLOW.max_retries:
            if current_retry > 0:
                logger.warning(
                    f"Retrying workflow execution (attempt {current_retry + 1}/{WORKFLOW.max_retries + 1})"
                )

            prompt = await self._generate_execution_prompt(current_retry)
            state = await self._execute_workflow_with_streaming(
                prompt, ctx=ctx, agent=agent
            )
            report: Report = state.report

            if report:
                await self._handle_execution_success(report, event_queue, updater)
                return

            current_retry += 1

        await self._handle_retry_exhaustion(current_retry - 1, event_queue, updater)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the orchestration workflow."""
        # Create TaskUpdater for proper A2A protocol lifecycle management
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        try:
            logger.debug("Workflow coordinator received alert diagnostics")
            remediation_request = self._extract_remediation_request_from_message(
                context.message
            )
            agent = AgentWorkflow(
                agents=[
                    workflow_coordinator,
                    alert_remediation_specialist,
                    report_generator_agent,
                ],
                root_agent=workflow_coordinator.name,  # TODO change cordinator to workflow orchestrator and update everywhere else accordingly
                initial_state=WorkflowState(request=remediation_request),
            )
            ctx = Context(workflow=agent)

            # Submit task if this is a new task (not a continuation)
            if not context.current_task:
                await updater.submit()

            # Mark task as started
            await updater.start_work()

            # Execute the workflow with retry tracking
            await self._execute_with_retry_tracking(
                event_queue, updater, ctx=ctx, agent=agent
            )

        except Exception as e:
            await self._handle_execution_exception(e, event_queue, updater)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation."""
        logger.info("Received cancellation request")

        # Create TaskUpdater for proper cancellation
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

        logger.info("Task cancelled")
