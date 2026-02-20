#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
REPOSITORY="testpypi"
TOKEN_ENV=""
SKIP_CHECKS=0
SKIP_BUILD=0
DRY_RUN=0
SKIP_EXISTING=1

TEST_PYPI_URL="https://test.pypi.org/legacy/"
PYPI_URL="https://upload.pypi.org/legacy/"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/publish.sh [options]

Options:
  --repository {testpypi|pypi}  Publish target (default: testpypi)
  --token-env NAME              Env var with API token
  --skip-checks                 Skip ruff + mypy + pytest
  --skip-build                  Skip build and twine check steps
  --no-skip-existing            Do not pass --skip-existing to twine upload
  --dry-run                     Run validations/build but do not upload
  -h, --help                    Show this message

Env:
  PYTHON_BIN                    Python executable (default: python3)
  TEST_PYPI_API_TOKEN           Default token env for --repository testpypi
  PYPI_API_TOKEN                Default token env for --repository pypi
EOF
}

require_python_module() {
  local module_name="$1"
  if ! "${PYTHON_BIN}" -c "import ${module_name}" >/dev/null 2>&1; then
    echo "Missing Python module: ${module_name}" >&2
    echo "Install dependencies with: ${PYTHON_BIN} -m pip install -e \".[dev]\"" >&2
    exit 1
  fi
}

run_checks() {
  echo "[publish] running quality gates..."
  "${PYTHON_BIN}" -m ruff check .
  "${PYTHON_BIN}" -m mypy src
  "${PYTHON_BIN}" -m pytest -q
}

clean_artifacts() {
  rm -rf build dist
  find . -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +
}

build_artifacts() {
  echo "[publish] building distribution artifacts..."
  clean_artifacts
  "${PYTHON_BIN}" -m build
  "${PYTHON_BIN}" -m twine check dist/*
}

resolve_repository_url() {
  if [[ "${REPOSITORY}" == "testpypi" ]]; then
    echo "${TEST_PYPI_URL}"
    return
  fi
  echo "${PYPI_URL}"
}

resolve_token_env() {
  if [[ -n "${TOKEN_ENV}" ]]; then
    echo "${TOKEN_ENV}"
    return
  fi
  if [[ "${REPOSITORY}" == "testpypi" ]]; then
    echo "TEST_PYPI_API_TOKEN"
    return
  fi
  echo "PYPI_API_TOKEN"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repository)
      REPOSITORY="$2"
      shift 2
      ;;
    --token-env)
      TOKEN_ENV="$2"
      shift 2
      ;;
    --skip-checks)
      SKIP_CHECKS=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --no-skip-existing)
      SKIP_EXISTING=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "${REPOSITORY}" != "testpypi" && "${REPOSITORY}" != "pypi" ]]; then
  echo "Invalid --repository value: ${REPOSITORY}" >&2
  exit 1
fi

if [[ "${SKIP_CHECKS}" -eq 0 ]]; then
  require_python_module "ruff"
  require_python_module "mypy"
  require_python_module "pytest"
fi

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  require_python_module "build"
  require_python_module "twine"
elif [[ "${DRY_RUN}" -eq 0 ]]; then
  require_python_module "twine"
fi

if [[ "${SKIP_CHECKS}" -eq 0 ]]; then
  run_checks
fi

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  build_artifacts
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[publish] dry-run enabled, upload skipped."
  echo "[publish] built files:"
  ls -1 dist/* 2>/dev/null || true
  exit 0
fi

repository_url="$(resolve_repository_url)"
token_env_name="$(resolve_token_env)"
token_value="${!token_env_name-}"

if [[ -z "${token_value}" ]]; then
  echo "Missing publish token in env var: ${token_env_name}" >&2
  exit 1
fi

twine_args=(
  upload
  --repository-url "${repository_url}"
  --non-interactive
)
if [[ "${SKIP_EXISTING}" -eq 1 ]]; then
  twine_args+=(--skip-existing)
fi
twine_args+=(dist/*)

echo "[publish] uploading to ${REPOSITORY} (${repository_url})..."
TWINE_USERNAME="__token__" TWINE_PASSWORD="${token_value}" "${PYTHON_BIN}" -m twine "${twine_args[@]}"

echo "[publish] done."
