# Build context must be the project root (see docker-compose.yml),
# because this image needs both fog/ and sensors/.
FROM python:3.11-slim

WORKDIR /app

COPY fog/requirements.txt ./fog/requirements.txt
RUN pip install --no-cache-dir -r fog/requirements.txt

COPY sensors ./sensors
COPY fog ./fog

WORKDIR /app/fog
CMD ["python", "fog_node.py"]
