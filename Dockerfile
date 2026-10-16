# Multi-stage Dockerfile for WordCraft WASM Web Application

# Stage 1: Build WordCraft WASM package using Rust & Trunk
FROM rust:1.80-slim-bookworm AS builder

# Install build dependencies, trunk, and wasm32 target
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN rustup target add wasm32-unknown-unknown
RUN cargo install trunk --version 0.18.5

WORKDIR /usr/src/wordcraft

# Copy workspace files
COPY Cargo.toml Cargo.lock rustfmt.toml clippy.toml Trunk.toml ./
COPY apps/ ./apps/
COPY crates/ ./crates/
COPY assets/ ./assets/

# Build WASM web application
WORKDIR /usr/src/wordcraft/apps/wordcraft-web
RUN trunk build --release

# Stage 2: Serve compiled web static files with Nginx Alpine
FROM nginx:alpine

# Remove default nginx web assets
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled WASM static site from builder
COPY --from=builder /usr/src/wordcraft/apps/wordcraft-web/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
