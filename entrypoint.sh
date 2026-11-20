#!/bin/sh
set -e

# Entrypoint script: determines Flask debug switch based on environment variable (production defaults off, fixes SEC-03)
#   ATP_DEBUG=1  -> enable debug (development/troubleshooting only, not recommended for production)
#   others       -> keep debug=False
# 守护：首次启动且 config.json 缺失时，从 example 复制一份，避免 IsADirectoryError / 500
if [ ! -f config.json ] && [ -f config.json.example ]; then
  cp config.json.example config.json
fi

exec "$@"
