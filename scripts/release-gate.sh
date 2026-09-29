#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
PYTHON_BIN="${PYTHON:-${ROOT_DIR}/.venv/bin/python}"
STARTED_AT="${SECONDS}"

step_number=0
step_total=11

die() {
  printf '\n[release-gate] ERROR: %s\n' "$*" >&2
  exit 1
}

step() {
  step_number=$((step_number + 1))
  printf '\n[%d/%d] %s\n' "${step_number}" "${step_total}" "$1"
  shift
  "$@"
}

cd "${ROOT_DIR}"

[[ -d .git ]] || die "run this from a Git checkout"
[[ -x "${PYTHON_BIN}" ]] || die "Python virtualenv not found at ${PYTHON_BIN}. Create/activate .venv or set PYTHON=/path/to/python."
command -v git >/dev/null 2>&1 || die "git is required"
command -v node >/dev/null 2>&1 || die "node is required"
command -v npm >/dev/null 2>&1 || die "npm is required"
[[ -d "${FRONTEND_DIR}/node_modules" ]] || die "frontend/node_modules is missing. Run: (cd frontend && npm ci)"

required_node_major="$(tr -d '[:space:]' < "${ROOT_DIR}/.nvmrc")"
current_node_major="$(node -p 'process.versions.node.split(".")[0]')"
[[ "${current_node_major}" == "${required_node_major}" ]] \
  || die "Node ${required_node_major}.x is required by .nvmrc; current major is ${current_node_major}. Run: nvm use"

printf '[release-gate] Wi-Fi Experience Monitor V1\n'
printf '[release-gate] Python: %s\n' "$("${PYTHON_BIN}" --version 2>&1)"
printf '[release-gate] Node:   %s\n' "$(node --version)"
printf '[release-gate] Commit: %s\n' "$(git rev-parse --short HEAD)"

step "Shell deployment syntax" \
  bash -n "${ROOT_DIR}/scripts/release-gate.sh" "${ROOT_DIR}/agent/install.sh"

step "Python lint — Server + Agent" \
  "${PYTHON_BIN}" -m ruff check server agent

step "Python formatting — Server + Agent" \
  "${PYTHON_BIN}" -m ruff format --check server agent

step "Server test suite" \
  "${PYTHON_BIN}" -m pytest server/tests

step "Agent test suite" \
  "${PYTHON_BIN}" -m pytest agent/tests

step "Legacy compatibility test suite" \
  "${PYTHON_BIN}" -m pytest tests

step "Frontend unit tests" \
  bash -c 'cd "$1" && npm test' _ "${FRONTEND_DIR}"

step "Frontend lint" \
  bash -c 'cd "$1" && npm run lint' _ "${FRONTEND_DIR}"

step "Frontend production build" \
  bash -c 'cd "$1" && npm run build' _ "${FRONTEND_DIR}"

step "Unstaged whitespace validation" \
  git diff --check

step "Staged whitespace validation" \
  git diff --cached --check

elapsed=$((SECONDS - STARTED_AT))
printf '\n[release-gate] PASS — all %d checks completed in %dm %02ds\n' \
  "${step_total}" "$((elapsed / 60))" "$((elapsed % 60))"
