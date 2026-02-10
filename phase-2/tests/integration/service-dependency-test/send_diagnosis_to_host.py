#!/usr/bin/env python3
"""
Send agent1's diagnosis to the host agent via A2A protocol for service dependency failure test.
"""

import asyncio

from common import DiagnosisSender


async def send_diagnosis_to_host():
    """Send the diagnosis from agent1 to the host agent."""
    # Create JSON diagnosis data
    diagnosis = {
        "incident_id": "c2VydmljZS1kZXBlbmRlbmN5LXRlc3QtMDAx",  # base64 encoded: service-dependency-test-001
        "namespace": "integration-test-ofridman",
        "alert": {
            "name": "FrontendHighErrorRate",
            "severity": "warning",
            "service": "frontend-web",
            "description": "Frontend service experiencing 95% HTTP 500 error rate",
        },
        "diagnostics_suggestions": """Diagnosis Summary: Frontend service is healthy but experiencing 95% HTTP 500 error rate due to failed dependency connection.

Frontend Service Status (HEALTHY):
- Pods: 2/2 READY and RUNNING
- CPU: 15%, Memory: 25% (normal levels)
- Health checks: PASSING

Root Cause Identified: Connection refused to backend-api:8080 - "Failed to connect to backend-api:8080 - Connection refused"

Dependency Chain: frontend-web (HEALTHY) → backend-api:8080 (CONNECTION REFUSED)

Recommendation: The problem is NOT in frontend-web. Investigate backend-api service:
1. Check if backend-api pods are running and ready
2. Verify backend-api service exists and has valid endpoints
3. Check backend-api logs for crashes or startup failures
4. Confirm backend-api is listening on port 8080""",
        "message_type": "remediation_request",
        "logs": [
            "Error Rate: 95% (HTTP 500)",
            "Failed Requests: 190/min",
            "Failed to connect to backend-api:8080 - Connection refused",
        ],
        "remediation_reports": None,  # First execution
    }

    sender = DiagnosisSender()
    await sender.send_diagnosis_json(diagnosis)


if __name__ == "__main__":
    asyncio.run(send_diagnosis_to_host())
