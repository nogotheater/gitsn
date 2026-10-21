FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && useradd --create-home --uid 10001 app
COPY --chown=app:app . .
RUN mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app/media /app/staticfiles
USER app
EXPOSE 8000
CMD ["python", "scripts/start_dev.py"]
