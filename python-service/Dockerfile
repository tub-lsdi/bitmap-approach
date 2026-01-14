FROM python:3.13-slim

# Install HiGHS solver binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends highs && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY uv.lock ./

RUN uv sync --frozen

COPY benchmark_cs_jp_lp.py ./
COPY benchmark_rs_jp.py ./
COPY benchmark_ai_rs_jp.py ./
COPY cs_jp_lp.py ./
COPY rs_jp.py ./

ENV PYTHONUNBUFFERED=1
