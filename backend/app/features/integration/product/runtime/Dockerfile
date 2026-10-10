FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
COPY requirements.lock /install/requirements.lock
RUN pip install --no-cache-dir -r /install/requirements.lock
COPY adapter.py /app/adapter.py
WORKDIR /tmp
USER 65534:65534
ENTRYPOINT ["python", "/app/adapter.py"]
