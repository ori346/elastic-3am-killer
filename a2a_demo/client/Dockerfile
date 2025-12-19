# Multi-stage build
FROM python:3.11-slim as builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Final stage
FROM python:3.11-slim

# Create application directory with broad permissions for OpenShift
RUN mkdir -p /app && \
    chmod -R 777 /app

WORKDIR /app

# Copy Python dependencies to a location accessible by any user
COPY --from=builder /root/.local /opt/app-root

# Copy application code
COPY client.py /app/

# Set permissions so any user can read and execute
RUN chmod -R 775 /app && \
    chmod -R 775 /opt/app-root

# Add local bin to PATH (OpenShift compatible)
ENV PATH=/opt/app-root/bin:$PATH
ENV PYTHONPATH=/opt/app-root/lib/python3.11/site-packages
ENV PYTHONUNBUFFERED=1
ENV HOME=/tmp

# Default environment variables
ENV MICROSERVICE_A_URL="http://microservice-a:8080"
ENV REQUEST_RATE=2.0

# Labels
LABEL maintainer="demo@example.com"
LABEL description="Client Simulator for OpenShift Demo"
LABEL version="1.0.0"

# Run the client
CMD ["python", "-u", "client.py"]
