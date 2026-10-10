FROM python:3.12-slim
WORKDIR /workspace
COPY requirements-dev.lock pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir -r requirements-dev.lock
RUN python -m playwright install --with-deps chromium
RUN useradd --create-home app && mkdir -p artifacts && chown -R app:app /workspace
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
