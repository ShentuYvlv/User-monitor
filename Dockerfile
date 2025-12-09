# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# PYTHONDONTWRITEBYTECODE 1: Prevents Python from writing .pyc files to disc
# PYTHONUNBUFFERED 1: Prevents Python from buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
# libpq-dev and gcc are needed for psycopg2 (PostgreSQL adapter)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Make sure static directory exists
RUN mkdir -p static/images/instagram

# Run the application
# Use uvicorn to serve the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
