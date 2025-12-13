FROM --platform=linux/amd64 python:3.11-alpine

ARG ENV=production

ENV ENV=${ENV} \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    UV_PROJECT_ENVIRONMENT=/code/.venv \
    PATH="/code/.venv/bin:${PATH}"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /code
COPY pyproject.toml /code/

RUN uv install --no-dev

COPY main.py /code

CMD ["python", "/code/main.py"]
