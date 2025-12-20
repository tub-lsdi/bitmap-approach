FROM golang:1.24-bookworm AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

# Enable CGO for DuckDB driver
RUN CGO_ENABLED=1 GOOS=linux go build -o /app/bin/server ./cmd/server

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root/

COPY --from=builder /app/bin/server .

ENV DUCKDB_PATH=/data/corpus.db

EXPOSE 8080

CMD ["./server"]
