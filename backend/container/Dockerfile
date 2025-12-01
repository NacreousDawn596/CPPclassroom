FROM python:3.11-slim

# Install g++ and build tools
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Expose port 8080 for the Worker to communicate with
EXPOSE 8080

# Run the Flask app
CMD ["python3", "app.py"]
