# Babel's live server: one FastAPI app serves the API and the browser app (web/) on one port.
# Built from the bundle that tools/build_deploy.py makes in dist/railway/ (code, the private runtime data and the demo
# cache), not from the repo root. Keys come from the host's environment variables, never from a file.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # the bundle carries only part of the cache: never fall back to rebuilding the runtime data from it
    BABEL_REQUIRE_RUNTIME=1

WORKDIR /app
COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements-lock.txt

COPY . .
# new API answers are cached in cache/ at run time, so the app user must be able to write there
RUN useradd --create-home babel && chown -R babel /app
USER babel

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn babel.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
