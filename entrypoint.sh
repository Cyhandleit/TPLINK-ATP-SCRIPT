#!/bin/sh
set -e

# Entrypoint script: determines Flask debug switch based on environment variable (production defaults off, fixes SEC-03)
#   ATP_DEBUG=1  -> enable debug (development/troubleshooting only, not recommended for production)
#   others       -> keep debug=False
if [ "${ATP_DEBUG:-0}" = "1" ]; then
  sed -i 's/debug=False/debug=True/' atp_web.py
fi

exec "$@"
