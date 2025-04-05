FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory explicitly
RUN mkdir -p data

# Create startup script that uses PORT environment variable
RUN echo '#!/bin/bash\n\
PORT=${PORT:-8000}\n\
exec uvicorn server:app --host 0.0.0.0 --port ${PORT}' > /app/start.sh && \
chmod +x /app/start.sh

# Run the startup script
CMD ["/app/start.sh"]