#!/bin/sh
# Ensure DATA_DIR exists and is writable by the non-root app user, then drop privileges.
set -eu
DATA_DIR="${DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser "$DATA_DIR" || true
    if command -v setpriv >/dev/null 2>&1; then
        exec setpriv --reuid=appuser --regid=appuser --init-groups -- "$@"
    fi
    exec su -s /bin/sh appuser -c 'exec "$0" "$@"' -- "$@"
fi

exec "$@"
