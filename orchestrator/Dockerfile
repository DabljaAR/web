FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY . .

# Use vendored deps — no network access needed during build
RUN go build -mod=vendor -o /orchestrator-server cmd/server/main.go

# Minimal production image
FROM alpine:latest
WORKDIR /app
COPY --from=builder /orchestrator-server /orchestrator-server

CMD ["/orchestrator-server"]
