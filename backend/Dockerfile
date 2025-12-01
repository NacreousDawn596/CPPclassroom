FROM debian:bookworm-slim

# Set working directory
WORKDIR /app

# Install Python, pip, g++, and necessary tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python3 -m venv /opt/venv

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies in virtual environment
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .

# Expose port
EXPOSE 5550

# Set environment variables
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python3", "app.py"]