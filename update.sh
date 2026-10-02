#!/usr/bin/env bash
# Mise à jour du container : pull de la dernière image publiée par la CI
# puis recreate. Les données (data/ : diapos + settings.json) survivent.
set -e
cd "$(dirname "$0")"
docker compose pull
docker compose up -d
docker image prune -f
