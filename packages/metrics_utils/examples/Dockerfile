FROM python:3.12-slim

WORKDIR /app

# Copy the metrics_utils package and install it
COPY packages/metrics_utils/ packages/metrics_utils/
RUN pip install --no-cache-dir packages/metrics_utils/

# Copy the sample client
COPY packages/metrics_utils/examples/sample_client.py sample_client.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "sample_client.py"]
