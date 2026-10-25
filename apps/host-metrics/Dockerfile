FROM python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY exporter.py mqtt_discovery.py mqtt_publisher.py /app/

USER 65534:65534

ENTRYPOINT ["python3", "/app/exporter.py"]
