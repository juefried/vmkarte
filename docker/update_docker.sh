#!/bin/bash
git pull && \
docker compose build --no-cache --pull && \
docker compose up -d
