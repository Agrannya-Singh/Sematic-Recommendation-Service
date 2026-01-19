# --- Phase 1: Builder (Compile/Install) ---
FROM python:3.11-slim as builder

WORKDIR /app

# Ensure we have updated pip
# We don't generally need build-base/gcc here because slim (Debian)
# usually has pre-built wheels for most packages (including grpcio).
RUN pip install --no-cache-dir --upgrade pip

COPY requirements_docker.txt .

# Install dependencies into a separate location
RUN pip install --no-cache-dir --prefix=/install -r requirements_docker.txt

# --- Phase 2: Runner (Runtime) ---
FROM python:3.11-slim

WORKDIR /app

# Create a non-root user for security
RUN useradd -m appuser && chown appuser /app

# Copy the installed dependencies from the builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Ensure DB exists (copy it in)
# COPY movies.db . # It is copied by COPY . .

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
