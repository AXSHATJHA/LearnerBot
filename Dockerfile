# Use a lightweight official Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements.txt first for efficient caching and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port FastAPI will run on (Render expects 8080)
EXPOSE 8080

# Start the FastAPI server (which also starts the Telegram bot in a thread)
CMD ["python", "bot.py"]
