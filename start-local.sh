#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
test -x .venv/bin/python || { echo 'Run sh setup.sh first.' >&2; exit 1; }
exec .venv/bin/python -m scripts.local_app start "$@"
