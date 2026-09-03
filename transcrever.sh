#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  echo "Ambiente virtual ausente. Execute os comandos de preparação do README.md." >&2
  exit 1
fi

export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PROJECT_DIR/.venv/bin/python" -m transcreve.cli "$@"
