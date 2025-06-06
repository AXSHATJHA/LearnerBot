# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Expose a port (not strictly needed for polling bots, but Render may require it)
EXPOSE 8080

# Start your bot
CMD ["python", "bot.py"]
