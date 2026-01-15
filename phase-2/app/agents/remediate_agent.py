"""
OpenShift Command Line Tools

Provides functions for executing 'oc' commands to gather cluster information.
These tools are used by the ReActAgent to investigate cluster state.
"""

import json
import os
import subprocess

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context
from llama_index.llms.openai_like import OpenAILike

# LLM Configuration - Remediation Agent specific environment variables with fallback to shared vars
API_BASE = os.getenv("REMEDIATION_AGENT_API_BASE", os.getenv("API_BASE"))
API_KEY = os.getenv("REMEDIATION_AGENT_API_KEY", os.getenv("API_KEY"))
MODEL = os.getenv("REMEDIATION_AGENT_MODEL", os.getenv("MODEL"))

# Tool usage tracking configuration
MAX_TOOLS = int(os.getenv("MAX_TOOLS", "5"))

# Module-level counter for tool usage (resets per agent execution)
_tool_usage_count = 0


def run_oc_command(command: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """
    Execute an oc command with standard error handling.

    Args:
        command: List of command arguments (e.g., ["oc", "get", "pods"])
        timeout: Timeout in seconds (default: 30)

    Returns:
        Tuple of (returncode, stdout, stderr)

    Raises:
        subprocess.TimeoutExpired: If command times out
        Exception: For other errors
    """
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def find_pod_by_name(
    pod_name: str, namespace: str, timeout: int = 30
) -> tuple[bool, str]:
    """
    Find a pod by exact or partial name match.

    Args:
        pod_name: Name of the pod (can be partial)
        namespace: OpenShift namespace
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, pod_name or error_message)
    """
    try:
        list_result = subprocess.run(
            [
                "oc",
                "get",
                "pods",
                "-n",
                namespace,
                "-o",
                "jsonpath={.items[*].metadata.name}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if list_result.returncode == 0:
            all_pods = list_result.stdout.split()
            # Try exact match first
            if pod_name in all_pods:
                return True, pod_name
            else:
                # Try partial match (e.g., "microservice-b" matches "microservice-b-698f45c955-hbkjz")
                matching_pods = [p for p in all_pods if p.startswith(pod_name)]
                if matching_pods:
                    actual_pod_name = matching_pods[0]  # Use first match
                    print(
                        f"Found pod '{actual_pod_name}' matching partial name '{pod_name}'"
                    )
                    return True, actual_pod_name
                else:
                    return (
                        False,
                        f"No pod found matching '{pod_name}' in namespace '{namespace}'",
                    )
        else:
            # Fallback to trying exact name
            return True, pod_name
    except subprocess.TimeoutExpired:
        return False, f"Timeout finding pod {pod_name}"
    except Exception as e:
        return False, f"Error finding pod: {str(e)}"


def compact_output(text: str) -> str:
    """
    Compact whitespace in text while preserving table structure.

    Args:
        text: Input text with potentially excessive whitespace

    Returns:
        Compacted text with single spaces
    """
    lines = text.strip().split("\n")
    compacted_lines = []
    for line in lines:
        # Replace multiple spaces with single space while preserving table structure
        compacted = " ".join(line.split())
        compacted_lines.append(compacted)
    return "\n".join(compacted_lines)


def track_tool_usage(func):
    """Decorator to track tool usage and enforce limit."""

    def wrapper(*args, **kwargs):
        global _tool_usage_count

        # Check if limit exceeded BEFORE executing the tool
        if _tool_usage_count >= MAX_TOOLS:
            return f"The tools called more than {MAX_TOOLS} (currently at {_tool_usage_count}). Please consolidate, create remediation plan and use write_remediation_plan - this is MANDATORY."

        # Increment the counter
        _tool_usage_count += 1

        # Call the original function
        result = func(*args, **kwargs)

        return result

    return wrapper


def reset_tool_usage_counter():
    """Reset the tool usage counter. Called at the start of each agent execution."""
    global _tool_usage_count
    _tool_usage_count = 0


llm = OpenAILike(
    api_base=API_BASE,
    api_key=API_KEY,
    model=MODEL,
    is_chat_model=True,
    max_tokens=1024,
    temperature=0.4,
    default_headers={"Content-Type": "application/json"},
    system_prompt=(
        "You are helping the AI Remediate Agent to remediate alerts in OpenShift cluster. "
        "The agent is not allowed to execute commands that modify the cluster state such as set, rollout, create, apply, edit, delete, expose, etc. "
        "The agent's role is to create commands that will resolve the alert in the cluster and handoff these commands back to Host Orchestrator agent."
    ),
)


@track_tool_usage
def execute_oc_get_pods(namespace: str) -> str:
    """
    Execute 'oc get pods' command for a specific namespace.
    Returns compacted output with minimal whitespace while preserving table structure.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        Compact pod listing
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pods", "-n", namespace]
        )
        if returncode == 0:
            return f"Pods in '{namespace}':\n" + compact_output(stdout)
        else:
            return f"Error getting pods: {stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get pods for namespace {namespace}"
    except Exception as e:
        return f"Error executing oc get pods: {str(e)}"


@track_tool_usage
def execute_oc_describe_pod(pod_name: str, namespace: str) -> str:
    """
    Get pod details with ONLY relevant fields for remediation (status, containers, resources).
    Optimized to minimize token usage. Supports partial pod names (e.g., "microservice-b" will find "microservice-b-698f45c955-hbkjz").

    Args:
        pod_name: Name of the pod to describe (can be partial, will search for matching pod)
        namespace: The OpenShift namespace

    Returns:
        Compact pod information with only essential fields
    """
    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return f"Error getting pod: {actual_pod_name}"

        # Get pod info using JSON output
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "pod", actual_pod_name, "-n", namespace, "-o", "json"]
        )

        if returncode != 0:
            return f"Error getting pod: {stderr}"

        pod_data = json.loads(stdout)

        # Build compact output
        output_lines = [f"Pod: {pod_data['metadata']['name']}"]
        output_lines.append(f"Status: {pod_data['status'].get('phase', 'Unknown')}")
        output_lines.append(
            f"ServiceAccount: {pod_data['spec'].get('serviceAccountName', 'default')}"
        )

        # Container info
        output_lines.append("\nContainers:")
        for container in pod_data["spec"].get("containers", []):
            output_lines.append(f"  - {container['name']}: {container['image']}")
            if "resources" in container:
                res = container["resources"]
                if "limits" in res:
                    output_lines.append(
                        f"    Limits: cpu={res['limits'].get('cpu', 'none')} mem={res['limits'].get('memory', 'none')}"
                    )
                if "requests" in res:
                    output_lines.append(
                        f"    Requests: cpu={res['requests'].get('cpu', 'none')} mem={res['requests'].get('memory', 'none')}"
                    )

        # Container statuses
        if "containerStatuses" in pod_data["status"]:
            output_lines.append("\nContainer Status:")
            for cs in pod_data["status"]["containerStatuses"]:
                state = (
                    list(cs.get("state", {}).keys())[0]
                    if cs.get("state")
                    else "unknown"
                )
                output_lines.append(
                    f"  - {cs['name']}: ready={cs.get('ready', False)} restarts={cs.get('restartCount', 0)} state={state}"
                )

        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc describe pod {pod_name}"
    except Exception as e:
        return f"Error executing oc describe pod: {str(e)}"


@track_tool_usage
def execute_oc_get_events(namespace: str, resource_name: str, tail: int = 10) -> str:
    """
    Execute 'oc get events' filtered by resource name for a specific namespace.
    Returns last N events matching the resource. Output is compacted to reduce token usage.

    Args:
        namespace: The OpenShift namespace to query
        resource_name: Resource name to filter events (e.g., "microservice-b") - REQUIRED
        tail: Number of recent events to return (default: 10 for token efficiency)

    Returns:
        Compact event listing (last N events for the specified resource)
    """
    try:
        # Use shell pipeline: oc get events | grep <resource> | tail -n <count>
        # This is more efficient than processing in Python
        cmd = f"oc get events -n {namespace} --sort-by='.lastTimestamp' | grep -i '{resource_name}' | tail -n {tail}"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # grep returns exit code 1 if no matches found
        if result.returncode == 1 or not result.stdout.strip():
            return f"No events found for resource '{resource_name}' in namespace '{namespace}'"

        if result.returncode != 0:
            return f"Error getting events: {result.stderr}"

        # Remove extra whitespace and compact output
        compacted = compact_output(result.stdout)
        lines_count = len(compacted.split("\n"))

        output = (
            f"Events for '{resource_name}' in '{namespace}' (last {lines_count}):\n"
        )
        output += compacted

        return output

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get events for namespace {namespace}"
    except Exception as e:
        return f"Error executing oc get events: {str(e)}"


@track_tool_usage
def execute_oc_logs(pod_name: str, namespace: str, pattern: str = "") -> str:
    """
    Execute 'oc logs' command for a specific pod.
    Returns only last 5 lines by default to minimize token usage.
    Supports partial pod names (e.g., "microservice-b" will find "microservice-b-698f45c955-hbkjz").

    Args:
        pod_name: Name of the pod (can be partial, will search for matching pod)
        namespace: The OpenShift namespace
        pattern: Optional text pattern to filter logs (uses grep)

    Returns:
        Command output as string (last 5 lines or filtered by pattern)
    """

    try:
        # Find the pod by exact name or partial match
        success, actual_pod_name = find_pod_by_name(pod_name, namespace)
        if not success:
            return f"Error getting logs: {actual_pod_name}"

        # If pattern is provided, use grep to filter logs
        if pattern:
            cmd = f"oc logs {actual_pod_name} -n {namespace} --tail=100 | grep -i '{pattern}' | tail -n 10"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # grep returns exit code 1 if no matches found
            if result.returncode == 1 or not result.stdout.strip():
                return f"No logs matching pattern '{pattern}' found for pod '{actual_pod_name}'"
            elif result.returncode != 0:
                return f"Error getting logs: {result.stderr}"
            else:
                return f"Logs for pod '{actual_pod_name}' matching pattern '{pattern}':\n{result.stdout}"
        else:
            # No pattern, return last 5 lines
            result = subprocess.run(
                ["oc", "logs", actual_pod_name, "-n", namespace, "--tail=5"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return (
                    f"Logs for pod '{actual_pod_name}' (last 5 lines):\n{result.stdout}"
                )
            else:
                return f"Error getting logs: {result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc logs for pod {pod_name}"
    except Exception as e:
        return f"Error executing oc logs: {str(e)}"


@track_tool_usage
def execute_oc_get_deployments(namespace: str) -> str:
    """
    Execute 'oc get deployments' command for a specific namespace.
    Returns compacted output with minimal whitespace while preserving table structure.

    Args:
        namespace: The OpenShift namespace to query

    Returns:
        Compact deployment listing
    """
    try:
        returncode, stdout, stderr = run_oc_command(
            ["oc", "get", "deployments", "-n", namespace]
        )
        if returncode == 0:
            return f"Deployments in '{namespace}':\n" + compact_output(stdout)
        else:
            return f"Error getting deployments: {stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get deployments for namespace {namespace}"
    except Exception as e:
        return f"Error executing oc get deployments: {str(e)}"


@track_tool_usage
def execute_oc_get_deployment_resources(deployment_name: str, namespace: str) -> str:
    """
    Execute 'oc get deployment' command to retrieve ONLY the container resource limits/requests.
    This is optimized to reduce token usage by extracting only what's needed for remediation.

    Args:
        deployment_name: Name of the deployment
        namespace: The OpenShift namespace

    Returns:
        Container resource configuration (limits and requests only)
    """
    try:
        # Use jsonpath to extract ONLY the container specs (resources, image, name)
        # This dramatically reduces token usage vs full YAML
        result = subprocess.run(
            [
                "oc",
                "get",
                "deployment",
                deployment_name,
                "-n",
                namespace,
                "-o",
                'jsonpath={range .spec.template.spec.containers[*]}{"Container: "}{.name}{"\\n"}{"Image: "}{.image}{"\\n"}{"Resources:\\n"}{.resources}{"\\n---\\n"}{end}',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                return f"Deployment '{deployment_name}' found but no container resource info available (may have no limits/requests set)"

            return (
                f"Resource configuration for deployment '{deployment_name}':\n{output}"
            )
        else:
            return f"Error getting deployment resources: {result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get deployment {deployment_name}"
    except Exception as e:
        return f"Error executing oc get deployment resources: {str(e)}"


@track_tool_usage
def execute_oc_describe_deployment(deployment_name: str, namespace: str) -> str:
    """
    Get deployment details with ONLY relevant fields (replicas, conditions, strategy).
    Optimized to minimize token usage by extracting only essential information.

    Args:
        deployment_name: Name of the deployment to describe
        namespace: The OpenShift namespace

    Returns:
        Compact deployment information with only essential fields
    """
    try:
        # Get deployment info using JSON output for compact extraction
        result = subprocess.run(
            ["oc", "get", "deployment", deployment_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return f"Error getting deployment: {result.stderr}"

        deploy_data = json.loads(result.stdout)

        # Build compact output
        output_lines = [f"Deployment: {deploy_data['metadata']['name']}"]

        # Replica status
        spec = deploy_data.get("spec", {})
        status = deploy_data.get("status", {})
        output_lines.append(
            f"Replicas: desired={spec.get('replicas', 0)} ready={status.get('readyReplicas', 0)} available={status.get('availableReplicas', 0)}"
        )

        # Strategy
        strategy = spec.get("strategy", {}).get("type", "Unknown")
        output_lines.append(f"Strategy: {strategy}")

        # Conditions (compact, only type and status)
        if "conditions" in status:
            output_lines.append("\nConditions:")
            for cond in status["conditions"]:
                output_lines.append(
                    f"  {cond.get('type', 'Unknown')}: {cond.get('status', 'Unknown')}"
                )

        return "\n".join(output_lines)

    except subprocess.TimeoutExpired:
        return f"Timeout executing oc get deployment {deployment_name}"
    except Exception as e:
        return f"Error executing oc describe deployment: {str(e)}"


async def get_microservices_info(ctx: Context) -> str:
    # TODO consider to enable the agent to do that by itself
    """
    Retrieve the microservices structure from the Context object.

    Args:
        ctx: The Context object containing microservices information.

    Returns:
        A string representation of the microservices structure.
    """
    state = await ctx.store.get("state")
    return state["microservices_info"]


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

    # Reset tool usage counter for the next invocation
    reset_tool_usage_counter()

    plan = {"explanation": explanation, "commands": commands}
    async with ctx.store.edit_state() as ctx_state:
        ctx_state["state"]["remediation_plan"] = plan
    return f"Stored remediation plan in context: {json.dumps(plan, indent=2)}. NOW YOU MUST HANDOFF TO 'Host Orchestrator' - this is MANDATORY."


tools = [
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
        - recommendation (str): Diagnose agent recommedations

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
          Example: "microservice-b has 128Mi memory limit causing OOMKilled. Increasing to 512Mi."
        - commands (list[str]): List of EXECUTABLE oc commands (NOT descriptions)
          Must be valid shell commands that modify cluster state

        Returns: Confirmation that plan was stored, then MANDATORY handoff instruction

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
        """,
    ),
    FunctionTool.from_defaults(
        fn=get_microservices_info,
        name="get_microservices_info",
        description="""Get microservices architecture information from context.

        Purpose: Understand the application structure and dependencies.

        Inputs: None - reads from context["microservices_info"]

        Returns: String describing microservices architecture

        When to call: In Step 0 to understand the application before investigation
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployment_resources,
        name="get_deployment_resources",
        description="""Get deployment resource configuration (CPU/memory limits and requests).

        Purpose: Check current resource allocations to identify if they need adjustment.

        Required Inputs:
        - deployment_name (str): Name of the deployment (e.g., "backend")
        - namespace (str): OpenShift namespace (e.g., "my-app")

        Returns: Container resource configuration showing limits and requests for CPU and memory

        Output format:
        Container: <name>
        Image: <image>
        Resources:
        Limits: cpu=X memory=Y
        Requests: cpu=X memory=Y

        When to call: When investigating resource-related alerts (OOMKilled, CPU throttling)
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_pods,
        name="execute_oc_get_pods",
        description="""List all pods in a namespace with their status.

        Purpose: See which pods are running, pending, or failed.

        Required Inputs:
        - namespace (str): OpenShift namespace to query

        Returns: Compact table of pods with NAME, READY, STATUS, RESTARTS, AGE

        When to call: When investigating pod-related issues or to see overall pod health
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_pod,
        name="execute_oc_describe_pod",
        description="""Get detailed pod information including status, containers, and resources.

        Purpose: Deep dive into a specific pod to diagnose issues.

        Required Inputs:
        - pod_name (str): Name of the pod (supports partial names like "microservice-auth")
        - namespace (str): OpenShift namespace

        Returns: Compact pod details including:
        - Pod status and phase
        - Container information with resource limits/requests
        - Container states and restart counts

        Features:
        - Supports partial pod names (e.g., "frontend" matches "frontend-698f45c955-hbkjz")
        - Automatically finds full pod name if partial match provided

        When to call: When investigating specific pod failures or container issues
        Note: Use execute_oc_get_events separately if you need event history
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_events,
        name="execute_oc_get_events",
        description="""Get recent Kubernetes events for a specific resource.

        Purpose: See what happened to a resource (pod, deployment) over time.

        Required Inputs:
        - namespace (str): OpenShift namespace
        - resource_name (str): Resource name to filter events (e.g., "microservice-b")
        - tail (int, optional): Number of recent events to return (default: 10)

        Returns: Last N events sorted by timestamp, filtered by resource name

        When to call: When investigating issues to see event history and warnings
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_logs,
        name="execute_oc_logs",
        description="""Get pod logs with optional pattern filtering.

        Purpose: Read application logs to diagnose errors or issues.

        Required Inputs:
        - pod_name (str): Name of the pod (supports partial names)
        - namespace (str): OpenShift namespace
        - pattern (str, optional): Text pattern to filter logs with grep

        Returns: Last 5 lines of logs (or last 10 matching lines if pattern provided)

        Features:
        - Supports partial pod names (auto-matches to full name)
        - Optional grep pattern filtering
        - Token-optimized (returns only recent/relevant logs)

        When to call: When investigating application errors or behavior
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_get_deployments,
        name="execute_oc_get_deployments",
        description="""List all deployments in a namespace with their status.

        Purpose: See deployment health and replica counts.

        Required Inputs:
        - namespace (str): OpenShift namespace to query

        Returns: Compact table of deployments with NAME, READY, UP-TO-DATE, AVAILABLE, AGE

        When to call: When investigating deployment-related issues or to see overall deployment health
        """,
    ),
    FunctionTool.from_defaults(
        fn=execute_oc_describe_deployment,
        name="execute_oc_describe_deployment",
        description="""Get detailed deployment information including replicas, strategy, and conditions.

        Purpose: Deep dive into a specific deployment to diagnose issues.

        Required Inputs:
        - deployment_name (str): Name of the deployment
        - namespace (str): OpenShift namespace

        Returns: Compact deployment details including:
        - Replica status (desired, ready, available)
        - Update strategy
        - Conditions (Available, Progressing, etc.)

        When to call: When investigating deployment rollout issues or replica problems
        Note: Use execute_oc_get_events separately if you need event history
        """,
    ),
]


system_prompt = f"""OpenShift remediation specialist. You are a TOOL-ONLY agent - you MUST NOT answer with text.

CRITICAL TOOL USAGE LIMIT:
- You have a maximum of {MAX_TOOLS} tool calls for investigation
- If you exceed {MAX_TOOLS} tools, you will be forced to create a remediation plan immediately
- Be strategic and efficient in your tool usage

MANDATORY WORKFLOW (execute ALL steps):
STEP 0: Collect information about the alert and the microservices
- Call get_microservices_info tool
- Call read_alert_diagnostics_data tool

STEP 2: Use your tools to collect new information about the project.
- Use execute_oc_get_pods, execute_oc_describe_pod, execute_oc_get_events, execute_oc_logs, execute_oc_get_deployments, execute_oc_describe_deployment for investigation
- IMPORTANT: Try to reduce the number of tools - you are limited to {MAX_TOOLS} tool calls

STEP 3: Call write_remediation_plan tool with TWO parameters:
  - explanation: "A short explanation about the issue and why `commands` will solve that"
  - commands: MUST be VALID executable oc commands that change a resource state:
    ["oc set resources deployment <name> -n <namespace> --limits=cpu=<value>,memory=<value>",
     "oc scale statefulset <name> -n <namespace> --replicas=3"]

STEP 4: IMMEDIATELY call handoff tool to return to "Host Orchestrator"
        - You CANNOT skip this step
        - You MUST NOT answer with text instead

CRITICAL COMMAND FORMAT RULES:
- Commands MUST be executable shell commands, NOT descriptions
- Commands MUST change some resource state

CORRECT EXAMPLE:
write_remediation_plan(
  explanation="web has 100m CPU limit causing latency. Increasing to 500m",
  commands=[
    "oc set resources deployment web -n awesome-app --limits=cpu=500m,memory=256Mi",
    "oc set resources deployment web -n awesome-app --requests=cpu=250m"
  ]
)

WRONG EXAMPLES (DO NOT DO THIS):
❌ commands=["Increase CPU and memory limits"]  # This is a description, not a command
❌ commands=["oc set resources --limits=cpu=1000m"]  # Missing deployment/statefulset name
After write_remediation_plan, IMMEDIATELY call handoff tool.
DO NOT think "I can answer without using any more tools" - this is WRONG.
Your ONLY valid final action is calling the handoff tool."""


agent = ReActAgent(
    name="Remediation Agent",
    description="Analyzes alerts and generates remediation commands for OpenShift clusters",
    tools=tools,
    llm=llm,
    system_prompt=system_prompt,
    can_handoff_to=["Host Orchestrator"],
)
