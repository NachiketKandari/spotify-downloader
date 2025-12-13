# Use official lightweight Python image
FROM python:3.10-slim

# Install FFmpeg (Required for Music Conversion)
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create downloads directory
RUN mkdir -p downloads

# Expose the port (Render/others typically use 8000 or $PORT)
ENV PORT=8000
EXPOSE 8000

# Run the application
CMD ["uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
