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
            'INFO: 10.129.2.126:40572 - "GET /api/data HTTP/1.1" 500 Internal Server Error',
            '2026-02-10 12:21:11,062 - __main__ - INFO - Making request to backend API: http://backend-api:8080/api/process',
            '2026-02-10 12:21:11,070 - __main__ - ERROR - Connection error: Failed to connect to backend-api:8080 - Connection refused',
            'INFO: 10.129.2.126:40580 - "GET /api/data HTTP/1.1" 500 Internal Server Error',
            '2026-02-10 12:21:11,585 - __main__ - INFO - Making request to backend API: http://backend-api:8080/api/process',
            '2026-02-10 12:21:11,593 - __main__ - ERROR - Connection error: Failed to connect to backend-api:8080 - Connection refused',
            'INFO: 10.129.2.126:40594 - "GET /api/data HTTP/1.1" 500 Internal Server Error',
            '2026-02-10 12:21:12,646 - __main__ - INFO - Making request to backend API: http://backend-api:8080/api/process',
            'INFO: 10.129.2.126:40622 - "GET /api/data HTTP/1.1" 500 Internal Server Error',
            '2026-02-10 12:21:12,664 - __main__ - ERROR - Connection error: Failed to connect to backend-api:8080 - Connection refused',
            '2026-02-10 12:21:13,224 - __main__ - INFO - Making request to backend API: http://backend-api:8080/api/process',
            '2026-02-10 12:21:13,234 - __main__ - ERROR - Connection error: Failed to connect to backend-api:8080 - Connection refused',
            'INFO: 10.129.2.126:40630 - "GET /api/data HTTP/1.1" 500 Internal Server Error',
            '2026-02-10 12:21:13,744 - __main__ - INFO - Making request to backend API: http://backend-api:8080/api/process',
            '2026-02-10 12:21:13,752 - __main__ - ERROR - Connection error: Failed to connect to backend-api:8080 - Connection refused',
            'INFO: 10.129.2.126:40646 - "GET /api/data HTTP/1.1" 500 Internal Server Error',
            'INFO: 10.129.2.2:47732 - "GET /ready HTTP/1.1" 200 OK',
            'INFO: 10.129.2.2:47734 - "GET /health HTTP/1.1" 200 OK',
        ],
        "remediation_reports": None,  # First execution
    }

    sender = DiagnosisSender()
    await sender.send_diagnosis_json(diagnosis)


if __name__ == "__main__":
    asyncio.run(send_diagnosis_to_host())
