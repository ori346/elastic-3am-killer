# Multi-stage build
FROM python:3.11-slim as builder

WORKDIR /app

COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt


# Final stage
FROM python:3.11-slim

# Install oc CLI
RUN apt-get update && \
    apt-get install -y curl tar && \
    curl -L https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz | tar -xz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/oc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create application directory with broad permissions for OpenShift
RUN mkdir -p /app && \
    chmod -R 777 /app

WORKDIR /app

# Copy Python dependencies to a location accessible by any user
COPY --from=builder /root/.local /opt/app-root

# Copy application code
COPY agent2.py /app/

# Set permissions so any user can read and execute
RUN chmod -R 775 /app && \
    chmod -R 775 /opt/app-root

# Add local bin to PATH (OpenShift compatible)
ENV PATH=/opt/app-root/bin:$PATH
ENV PYTHONPATH=/opt/app-root/lib/python3.11/site-packages
ENV PYTHONUNBUFFERED=1
ENV HOME=/tmp

# Labels
LABEL maintainer="demo@example.com"
LABEL description="Agent 2 - Remediate Agent for OpenShift A2A Demo"
LABEL version="1.0.0"

# Run the agent
CMD ["python", "-u", "agent2.py"]
