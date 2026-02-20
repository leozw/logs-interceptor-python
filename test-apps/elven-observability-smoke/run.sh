#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
  echo "Missing .env at ${SCRIPT_DIR}/.env" >&2
  if [[ -f "${SCRIPT_DIR}/.env.example" ]]; then
    echo "Create it with: cp ${SCRIPT_DIR}/.env.example ${SCRIPT_DIR}/.env" >&2
  fi
  exit 1
fi

set -a
source "${SCRIPT_DIR}/.env"
set +a

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

python3 "${SCRIPT_DIR}/app.py"
