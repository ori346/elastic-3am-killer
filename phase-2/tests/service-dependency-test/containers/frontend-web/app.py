#!/usr/bin/env python3
"""
Frontend Web Application for Service Dependency Test.
This service depends on backend-api and will fail when backend is unavailable.
"""
import logging
import os
import time
from datetime import datetime

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Histogram,
                               generate_latest)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend-api:8080")
PORT = int(os.getenv("PORT", "8080"))
SERVICE_NAME = "frontend-web"

# Prometheus metrics
http_requests_total = Counter(
    "frontend_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration = Histogram(
    "frontend_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

backend_requests_total = Counter(
    "frontend_backend_requests_total", "Total requests to backend API", ["status"]
)

# Application state
app_start_time = time.time()
is_ready = True

app = FastAPI(title="Frontend Web Service", version="1.0")


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Middleware to collect Prometheus metrics."""
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    method = request.method
    endpoint = request.url.path
    status = str(response.status_code)

    # Record metrics
    http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    http_request_duration.labels(method=method, endpoint=endpoint).observe(duration)

    return response


@app.get("/health")
async def health_check():
    """Health check endpoint - always healthy regardless of backend status."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - app_start_time,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint - ready when service is initialized."""
    if not is_ready:
        raise HTTPException(status_code=503, detail="Service not ready")

    return {
        "status": "ready",
        "service": SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


@app.get("/api/data")
async def get_data():
    """Main endpoint that depends on backend API."""
    start_time = time.time()

    try:
        # Make request to backend API
        logger.info(f"Making request to backend API: {BACKEND_API_URL}/api/process")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BACKEND_API_URL}/api/process")
            response.raise_for_status()

            backend_data = response.json()
            backend_requests_total.labels(status="success").inc()

            logger.info("Successfully received data from backend API")

            # Return processed data
            return {
                "status": "success",
                "frontend_service": SERVICE_NAME,
                "backend_data": backend_data,
                "timestamp": datetime.utcnow().isoformat(),
                "response_time_ms": (time.time() - start_time) * 1000,
            }

    except httpx.ConnectError as e:
        # Connection refused - backend is down
        logger.error(f"Connection error: {e}")
        backend_requests_total.labels(status="connection_error").inc()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "Backend service unavailable",
                "message": e,
                "backend_url": BACKEND_API_URL,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except httpx.TimeoutException as e:
        # Backend timeout
        logger.error(f"Timeout error: {e}")
        backend_requests_total.labels(status="timeout").inc()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "Backend service timeout",
                "message": e,
                "backend_url": BACKEND_API_URL,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        # Other errors
        error_msg = f"Backend API error: {str(e)}"
        logger.error(f"Backend API error: {error_msg}")
        backend_requests_total.labels(status="error").inc()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "Backend service error",
                "message": error_msg,
                "backend_url": BACKEND_API_URL,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": SERVICE_NAME,
        "status": "running",
        "backend_api": BACKEND_API_URL,
        "endpoints": ["/health", "/ready", "/metrics", "/api/data"],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "path": str(request.url.path),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


if __name__ == "__main__":
    logger.info(f"Starting {SERVICE_NAME} on port {PORT}")
    logger.info(f"Backend API URL: {BACKEND_API_URL}")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", access_log=True)
