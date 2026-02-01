# Base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 5050

# Run the application with Gunicorn
# Initializes DB and Admin user before starting workers
CMD ["sh", "-c", "python3 -c 'from app import ensure_default_admin; import database; database.init_db(); ensure_default_admin()' && gunicorn --bind 0.0.0.0:5050 --workers 4 --threads 2 --access-logfile - --error-logfile - app:app"]