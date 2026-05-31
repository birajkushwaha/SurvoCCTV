FROM python:3.12-slim

# Install system dependencies for OpenCV headless execution
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install project dependencies
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    ultralytics \
    opencv-python-headless \
    jinja2

# Copy code modules
COPY backend /app/backend
COPY frontend /app/frontend
COPY data /app/data

# Expose API ports
EXPOSE 8000
EXPOSE 7860

# Headless configuration for OpenCV
ENV QT_QPA_PLATFORM=offscreen

# Run FastAPI app (reads $PORT or defaults to 8000)
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
