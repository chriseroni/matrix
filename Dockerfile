# Use an official Python runtime as a parent image
FROM python:3.8-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy your Python script to the container
COPY matrixasyncWithFile.py.py /app/matrixasyncWithFile.py.py

# Install required Python packages using pip
RUN pip install nio asyncio-mqtt paho-mqtt

# Run your Python script when the container launches
CMD ["python", "matrixasyncWithFile.py.py"]
