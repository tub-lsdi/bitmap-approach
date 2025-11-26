FROM python:3.11-slim

# Set working directory
WORKDIR /app

RUN pip install uv

# Copy project files
COPY pyproject.toml ./
COPY cs_jp_lp.py ./
COPY benchmark_cs_jp_lp.py ./
COPY data/bench_data/ ./data/bench_data/

# Install dependencies
RUN uv pip install --system pulp loguru

# Create results directory
RUN mkdir -p data/bench_results

# Set environment variables
ENV PYTHONUNBUFFERED=1

