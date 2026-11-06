FROM golang:1.23-alpine AS build

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/auth .

FROM alpine:3.21

RUN addgroup -S -g 10001 auth \
    && adduser -S -D -H -u 10001 -G auth auth

COPY --from=build /out/auth /usr/local/bin/auth

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/auth"]
