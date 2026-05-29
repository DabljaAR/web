# Stage 1: Build
FROM rust:1-slim-bookworm AS builder

RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache dependency compilation: copy manifests first, build dummy binary
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release 2>&1 || true
RUN rm -f src/main.rs

# Build real binary
COPY src ./src
RUN touch src/main.rs
RUN cargo build --release

# Stage 2: Runtime
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/target/release/media-service ./media-service
RUN mkdir -p /tmp/media-service

EXPOSE 8001
CMD ["./media-service"]
