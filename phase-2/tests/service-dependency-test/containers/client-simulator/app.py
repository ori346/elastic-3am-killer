#!/usr/bin/env python3
"""
Client Simulator for Service Dependency Test.
This service generates HTTP requests to the frontend web service to trigger error scenarios.
"""
import asyncio
import logging
import os
import random
import time
from datetime import datetime
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Gauge, Histogram,
                               generate_latest)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_SERVICE = os.getenv("TARGET_SERVICE", "frontend-web:8080")
REQUEST_RATE = float(os.getenv("REQUEST_RATE", "2.0"))  # requests per second
PORT = int(os.getenv("PORT", "8081"))
SERVICE_NAME = "client-simulator"

# Prometheus metrics
requests_sent_total = Counter(
    "client_requests_sent_total",
    "Total requests sent to target service",
    ["target", "status"],
)

request_duration = Histogram(
    "client_request_duration_seconds", "Request duration in seconds", ["target"]
)

active_connections = Gauge("client_active_connections", "Number of active connections")

target_service_up = Gauge(
    "client_target_service_up", "Whether the target service is reachable (1=up, 0=down)"
)

# Application state
app_start_time = time.time()
is_running = False
total_requests_sent = 0
total_successes = 0
total_errors = 0

app = FastAPI(title="Client Simulator", version="1.0")


class ClientSimulator:
    def __init__(self):
        self.target_url = f"http://{TARGET_SERVICE}"
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

    async def make_request(self) -> dict:
        """Make a single request to the target service."""
        global total_requests_sent, total_successes, total_errors

        start_time = time.time()
        total_requests_sent += 1

        try:
            active_connections.inc()

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.target_url}/api/data")

                duration = time.time() - start_time
                request_duration.labels(target=TARGET_SERVICE).observe(duration)

                if response.status_code == 200:
                    total_successes += 1
                    requests_sent_total.labels(
                        target=TARGET_SERVICE, status="success"
                    ).inc()
                    target_service_up.set(1)

                    logger.info(
                        f"Request #{total_requests_sent}: SUCCESS (200) in {duration:.3f}s"
                    )
                    return {
                        "status": "success",
                        "status_code": response.status_code,
                        "duration_ms": duration * 1000,
                        "response_size": len(response.content),
                    }
                else:
                    total_errors += 1
                    requests_sent_total.labels(
                        target=TARGET_SERVICE, status=f"http_{response.status_code}"
                    ).inc()

                    logger.warning(
                        f"Request #{total_requests_sent}: HTTP {response.status_code} in {duration:.3f}s"
                    )

                    if response.status_code >= 500:
                        target_service_up.set(0)

                    return {
                        "status": "error",
                        "status_code": response.status_code,
                        "duration_ms": duration * 1000,
                        "error": f"HTTP {response.status_code}",
                    }

        except httpx.ConnectError as e:
            duration = time.time() - start_time
            total_errors += 1
            requests_sent_total.labels(
                target=TARGET_SERVICE, status="connection_error"
            ).inc()
            target_service_up.set(0)

            logger.error(f"Request #{total_requests_sent}: CONNECTION ERROR - {str(e)}")
            return {
                "status": "connection_error",
                "duration_ms": duration * 1000,
                "error": str(e),
            }

        except Exception as e:
            duration = time.time() - start_time
            total_errors += 1
            requests_sent_total.labels(target=TARGET_SERVICE, status="error").inc()
            target_service_up.set(0)

            logger.error(f"Request #{total_requests_sent}: ERROR - {str(e)}")
            return {"status": "error", "duration_ms": duration * 1000, "error": str(e)}

        finally:
            active_connections.dec()

    async def run_simulation(self):
        """Run the continuous request simulation."""
        logger.info(f"Starting request simulation to {self.target_url}")
        logger.info(f"Request rate: {REQUEST_RATE} requests/second")

        interval = 1.0 / REQUEST_RATE

        while self.is_running:
            try:
                # Make request
                await self.make_request()

                # Wait for next request
                await asyncio.sleep(interval)

                # Add some jitter to make it more realistic
                jitter = random.uniform(-0.1, 0.1) * interval
                if jitter > 0:
                    await asyncio.sleep(jitter)

            except Exception as e:
                logger.error(f"Simulation error: {str(e)}")
                await asyncio.sleep(interval)

    async def start(self):
        """Start the simulation."""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.run_simulation())
            logger.info("Client simulation started")

    async def stop(self):
        """Stop the simulation."""
        if self.is_running:
            self.is_running = False
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
            logger.info("Client simulation stopped")


# Global simulator instance
simulator = ClientSimulator()


@app.on_event("startup")
async def startup_event():
    """Start the simulation on app startup."""
    global is_running
    is_running = True
    await simulator.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the simulation on app shutdown."""
    global is_running
    is_running = False
    await simulator.stop()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - app_start_time,
        "simulation_running": simulator.is_running,
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
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


@app.get("/status")
async def simulation_status():
    """Get simulation status and statistics."""
    uptime = time.time() - app_start_time
    success_rate = (
        (total_successes / total_requests_sent * 100) if total_requests_sent > 0 else 0
    )
    error_rate = (
        (total_errors / total_requests_sent * 100) if total_requests_sent > 0 else 0
    )

    return {
        "service": SERVICE_NAME,
        "simulation_running": simulator.is_running,
        "target_service": TARGET_SERVICE,
        "request_rate": REQUEST_RATE,
        "statistics": {
            "uptime_seconds": uptime,
            "total_requests": total_requests_sent,
            "total_successes": total_successes,
            "total_errors": total_errors,
            "success_rate_percent": round(success_rate, 2),
            "error_rate_percent": round(error_rate, 2),
            "requests_per_minute": (
                round(total_requests_sent / (uptime / 60), 2) if uptime > 0 else 0
            ),
        },
        "configuration": {
            "target_url": simulator.target_url,
            "request_rate": REQUEST_RATE,
            "port": PORT,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/start")
async def start_simulation():
    """Start the request simulation."""
    await simulator.start()
    return {"message": "Simulation started", "status": "running"}


@app.post("/stop")
async def stop_simulation():
    """Stop the request simulation."""
    await simulator.stop()
    return {"message": "Simulation stopped", "status": "stopped"}


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": SERVICE_NAME,
        "status": "running",
        "target_service": TARGET_SERVICE,
        "request_rate": REQUEST_RATE,
        "simulation_running": simulator.is_running,
        "endpoints": ["/health", "/ready", "/metrics", "/status", "/start", "/stop"],
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    logger.info(f"Starting {SERVICE_NAME} on port {PORT}")
    logger.info(f"Target service: {TARGET_SERVICE}")
    logger.info(f"Request rate: {REQUEST_RATE} requests/second")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", access_log=True)
