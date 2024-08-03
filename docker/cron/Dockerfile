# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Install cron
RUN apt-get update && apt-get install -y \
    cron \
    && apt-get clean

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
#COPY script.py /app/script.p
COPY requirements.txt /app/requirements.txt
COPY src/data_grabber/data_grabber.py /app/data_grabber.py
COPY src/data_grabber/libs/* /app/libs/

COPY docker/cron/crontab /etc/cron.d/my-cron
RUN chmod 0600 /etc/cron.d/my-cron
# Registriere die Crontab-Datei
RUN crontab /etc/cron.d/my-cron

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Run the command on container startup
CMD ["cron", "-f", "-l", "2"]
