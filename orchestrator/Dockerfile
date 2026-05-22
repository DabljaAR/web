FROM golang:1.21-alpine AS builder

WORKDIR /app

# Copy the source code first so tidy knows what we're importing
COPY . .

# Fetch and tidy dependencies
RUN go mod tidy
RUN go mod download

# Build the Go app
RUN go build -o /orchestrator-server cmd/server/main.go

# Minimal production image
FROM alpine:latest
WORKDIR /app
COPY --from=builder /orchestrator-server /orchestrator-server

CMD ["/orchestrator-server"]
