#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.11+ and Node.js 24 LTS first.' >&2; exit 1; }
exec python3 -m scripts.local_app setup "$@"
