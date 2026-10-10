# Build only this directory. No .env, repository checkout or host credentials.
FROM python:3.12-slim
RUN pip install --no-cache-dir \
    https://github.com/jsvine/pdfplumber/archive/4c64b92d5caccd71c645e98e0fabb0c4dba7ff45.tar.gz \
    https://github.com/frictionlessdata/frictionless-py/archive/2a30fbd5a7d9ace96b121494624b970e56a72a0f.tar.gz
WORKDIR /tmp
COPY independent.py /proof/independent.py
USER 65534:65534
ENTRYPOINT ["python", "/proof/independent.py"]
