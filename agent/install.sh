#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="wifi-experience-agent"
SERVICE_USER="wifi-experience-agent"
SERVICE_GROUP="wifi-experience-agent"
INSTALL_ROOT="/opt/wifi-experience-agent"
VENV_DIR="${INSTALL_ROOT}/venv"
CONFIG_DIR="/etc/wifi-experience-agent"
ENV_FILE="${CONFIG_DIR}/agent.env"
DATA_DIR="/var/lib/wifi-experience-agent"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_URL=""
ENROLLMENT_TOKEN=""
INTERFACE=""
AGENT_NAME="$(hostname)"
IMPORT_DATA_DIR=""
START_SERVICE=true

usage() {
  cat <<'EOF'
Install Wi-Fi Experience Monitor Agent as a systemd service.

Usage:
  sudo ./agent/install.sh \
    --server-url http://127.0.0.1:8000 \
    --interface wlp0s20f3 \
    [--enrollment-token TOKEN] \
    [--name sensor-local-01] \
    [--import-data-dir ./data/agent] \
    [--no-start]

Options:
  --server-url URL        Server URL used by this Agent.
  --interface IFACE       Wi-Fi interface monitored by this Agent.
  --enrollment-token TOKEN
                          Enrollment token for a new identity. May be omitted
                          when importing or reusing an existing agent.db.
  --name NAME             Agent display name. Defaults to the hostname.
  --import-data-dir PATH  Copy an existing Agent data directory into the
                          persistent system service data directory.
  --no-start              Install and enable the service without starting it.
  -h, --help              Show this help.

Stop any manually running wifi-agent process before importing its data directory.
EOF
}

die() {
  printf '[agent-install] ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '[agent-install] %s\n' "$*"
}

quote_env() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-url)
      [[ $# -ge 2 ]] || die "--server-url requires a value"
      SERVER_URL="$2"
      shift 2
      ;;
    --interface)
      [[ $# -ge 2 ]] || die "--interface requires a value"
      INTERFACE="$2"
      shift 2
      ;;
    --enrollment-token)
      [[ $# -ge 2 ]] || die "--enrollment-token requires a value"
      ENROLLMENT_TOKEN="$2"
      shift 2
      ;;
    --name)
      [[ $# -ge 2 ]] || die "--name requires a value"
      AGENT_NAME="$2"
      shift 2
      ;;
    --import-data-dir)
      [[ $# -ge 2 ]] || die "--import-data-dir requires a value"
      IMPORT_DATA_DIR="$2"
      shift 2
      ;;
    --no-start)
      START_SERVICE=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "run this installer with sudo or as root"
[[ -n "${SERVER_URL}" ]] || die "--server-url is required"
[[ -n "${INTERFACE}" ]] || die "--interface is required"
[[ "${SERVER_URL}" != *$'\n'* ]] || die "server URL must not contain newlines"
[[ "${INTERFACE}" != *$'\n'* ]] || die "interface must not contain newlines"
[[ "${AGENT_NAME}" != *$'\n'* ]] || die "agent name must not contain newlines"
[[ "${ENROLLMENT_TOKEN}" != *$'\n'* ]] || die "enrollment token must not contain newlines"

for command_name in python3 systemctl useradd groupadd getent install iw ip ping curl; do
  require_command "${command_name}"
done

python3 -m venv --help >/dev/null 2>&1 \
  || die "python3 venv support is required (Ubuntu package: python3-venv)"

ip link show dev "${INTERFACE}" >/dev/null 2>&1 \
  || die "network interface does not exist: ${INTERFACE}"
iw dev "${INTERFACE}" info >/dev/null 2>&1 \
  || die "interface is not available through nl80211/iw: ${INTERFACE}"

if [[ -n "${IMPORT_DATA_DIR}" ]]; then
  IMPORT_DATA_DIR="$(realpath "${IMPORT_DATA_DIR}")"
  [[ -d "${IMPORT_DATA_DIR}" ]] || die "import data directory does not exist: ${IMPORT_DATA_DIR}"
  [[ -f "${IMPORT_DATA_DIR}/agent.db" ]] \
    || die "import data directory does not contain agent.db: ${IMPORT_DATA_DIR}"
fi

if getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
  log "service group already exists: ${SERVICE_GROUP}"
else
  groupadd --system "${SERVICE_GROUP}"
  log "created service group: ${SERVICE_GROUP}"
fi

if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  log "service user already exists: ${SERVICE_USER}"
else
  useradd \
    --system \
    --gid "${SERVICE_GROUP}" \
    --home-dir "${DATA_DIR}" \
    --shell /usr/sbin/nologin \
    "${SERVICE_USER}"
  log "created service user: ${SERVICE_USER}"
fi

install -d -o root -g root -m 0755 "${INSTALL_ROOT}"
install -d -o root -g root -m 0755 "${CONFIG_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0700 "${DATA_DIR}"

if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
  log "stopping existing ${SERVICE_NAME} service for upgrade"
  systemctl stop "${SERVICE_NAME}.service"
fi

if [[ -n "${IMPORT_DATA_DIR}" ]]; then
  log "importing existing Agent state from ${IMPORT_DATA_DIR}"
  cp -a "${IMPORT_DATA_DIR}/." "${DATA_DIR}/"
  chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${DATA_DIR}"
  find "${DATA_DIR}" -type d -exec chmod 0700 {} +
  find "${DATA_DIR}" -type f -exec chmod 0600 {} +
fi

if [[ -z "${ENROLLMENT_TOKEN}" && ! -f "${DATA_DIR}/agent.db" ]]; then
  die "a new installation requires --enrollment-token or --import-data-dir containing agent.db"
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  log "creating service virtualenv"
  python3 -m venv "${VENV_DIR}"
fi

log "installing Agent package into ${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --quiet --upgrade "${ROOT_DIR}/agent"

umask 077
{
  printf 'WEM_AGENT_SERVER_URL=%s\n' "$(quote_env "${SERVER_URL%/}")"
  if [[ -n "${ENROLLMENT_TOKEN}" ]]; then
    printf 'WEM_AGENT_ENROLLMENT_TOKEN=%s\n' "$(quote_env "${ENROLLMENT_TOKEN}")"
  fi
  printf 'WEM_AGENT_DATA_DIR=%s\n' "$(quote_env "${DATA_DIR}")"
  printf 'WEM_AGENT_NAME=%s\n' "$(quote_env "${AGENT_NAME}")"
  printf 'WEM_AGENT_TYPE=%s\n' "$(quote_env "sensor")"
  printf 'WEM_AGENT_INTERFACE=%s\n' "$(quote_env "${INTERFACE}")"
} > "${ENV_FILE}"
chown root:root "${ENV_FILE}"
chmod 0600 "${ENV_FILE}"

install -o root -g root -m 0644 \
  "${ROOT_DIR}/agent/deploy/wifi-experience-agent.service" \
  "${UNIT_FILE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service" >/dev/null

if [[ "${START_SERVICE}" != true ]]; then
  log "installation complete; service enabled but not started"
  log "start with: sudo systemctl start ${SERVICE_NAME}"
  exit 0
fi

log "starting ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}.service"

for _ in {1..20}; do
  if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    log "service is active"
    systemctl --no-pager --full status "${SERVICE_NAME}.service" || true
    log "follow logs with: sudo journalctl -u ${SERVICE_NAME} -f"
    exit 0
  fi
  sleep 0.5
done

systemctl --no-pager --full status "${SERVICE_NAME}.service" || true
journalctl -u "${SERVICE_NAME}.service" -n 40 --no-pager || true
die "service did not become active"
