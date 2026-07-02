FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go mod vendor \
    && go build -mod=vendor -o /orchestrator-server cmd/server/main.go

# Minimal production image
FROM alpine:3.20
RUN apk add --no-cache curl ca-certificates
WORKDIR /app
COPY --from=builder /orchestrator-server /orchestrator-server

USER 1000

CMD ["/orchestrator-server"]
