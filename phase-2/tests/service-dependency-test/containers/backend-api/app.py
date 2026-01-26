#!/usr/bin/env python3
"""
Backend API Service for Service Dependency Test.
This service provides API endpoints for the frontend web service.
"""
import logging
import os
import random
import time
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
PORT = int(os.getenv("PORT", "8080"))
SERVICE_NAME = "backend-api"

# Prometheus metrics
http_requests_total = Counter(
    "backend_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration = Histogram(
    "backend_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

api_processing_requests = Counter(
    "backend_api_processing_requests_total", "Total API processing requests"
)

# Application state
app_start_time = time.time()
is_ready = True
request_count = 0

app = FastAPI(title="Backend API Service", version="1.0")


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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - app_start_time,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    if not is_ready:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

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


@app.get("/api/process")
async def process_data():
    """Main API endpoint for processing data."""
    global request_count
    request_count += 1

    # Increment processing counter
    api_processing_requests.inc()

    # Simulate some processing time (50-200ms)
    processing_time = random.uniform(0.05, 0.2)
    await asyncio.sleep(processing_time)

    logger.info(f"Processing request #{request_count}")

    # Return processed data
    return {
        "status": "success",
        "service": SERVICE_NAME,
        "request_id": request_count,
        "processing_time_ms": processing_time * 1000,
        "data": {
            "processed_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "result": f"Processed data item #{request_count}",
            "metadata": {
                "server_time": datetime.utcnow().isoformat(),
                "uptime_seconds": time.time() - app_start_time,
                "total_requests": request_count,
            },
        },
    }


@app.get("/api/status")
async def api_status():
    """API status endpoint with detailed information."""
    return {
        "service": SERVICE_NAME,
        "status": "operational",
        "version": "1.0",
        "uptime_seconds": time.time() - app_start_time,
        "total_requests_processed": request_count,
        "endpoints": {
            "/health": "Health check",
            "/ready": "Readiness check",
            "/metrics": "Prometheus metrics",
            "/api/process": "Main processing endpoint",
            "/api/status": "Service status information",
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": SERVICE_NAME,
        "status": "running",
        "version": "1.0",
        "endpoints": ["/health", "/ready", "/metrics", "/api/process", "/api/status"],
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
            "service": SERVICE_NAME,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


if __name__ == "__main__":
    import asyncio

    logger.info(f"Starting {SERVICE_NAME} on port {PORT}")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", access_log=True)
