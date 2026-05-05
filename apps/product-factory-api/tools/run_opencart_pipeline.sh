#!/usr/bin/env bash
set -euo pipefail

# Must remain LF-encoded because the publish service executes this via Bash/WSL.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.secrets/opencart.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # Accept CRLF-formatted env files from Windows editors.
  # shellcheck disable=SC1090
  set -a
  source <(tr -d '\r' < "${ENV_FILE}")
  set +a
fi

MODEL="${1:-${MODEL:-}}"
PRODUCT_FILE="${CURRENT_JOB_PRODUCT_FILE:-${REPO_ROOT}/products/${MODEL}.csv}"
MAIN_IMAGE="${REPO_ROOT}/work/${MODEL}/scrape/gallery/${MODEL}-1.jpg"
UPLOAD_REPORT="${REPO_ROOT}/work/${MODEL}/upload.opencart.json"
IMPORT_REPORT="${REPO_ROOT}/work/${MODEL}/import.opencart.json"

log() {
  echo "[opencart-publish] $*"
}

fail() {
  local stage="$1"
  local exit_code="$2"
  local message="$3"
  log "stage=${stage} status=failed message=${message}"
  log "upload_report=${UPLOAD_REPORT}"
  log "import_report=${IMPORT_REPORT}"
  exit "${exit_code}"
}

if [[ -z "${MODEL}" ]]; then
  fail "preflight" 11 "missing model. Usage: $0 123456"
fi

if [[ ! "${MODEL}" =~ ^[0-9]{6}$ ]]; then
  fail "preflight" 11 "model must be exactly 6 digits: ${MODEL}"
fi

if [[ ! -f "${PRODUCT_FILE}" ]]; then
  fail "preflight" 11 "missing product CSV: ${PRODUCT_FILE}"
fi

if [[ ! -f "${MAIN_IMAGE}" ]]; then
  fail "preflight" 11 "missing gallery image: ${MAIN_IMAGE}"
fi

log "stage=preflight status=ok model=${MODEL} product_file=${PRODUCT_FILE}"
log "upload_report=${UPLOAD_REPORT}"
log "import_report=${IMPORT_REPORT}"

log "stage=image_upload status=running"
if ! bash "${SCRIPT_DIR}/run_opencart_image_upload.sh" "${MODEL}"; then
  fail "image_upload" 12 "OpenCart image upload failed for model ${MODEL}"
fi
log "stage=image_upload status=ok"

log "stage=csv_import status=running"
if ! bash "${SCRIPT_DIR}/run_opencart_import_csv.sh" "${MODEL}"; then
  fail "csv_import" 13 "OpenCart CSV import failed for model ${MODEL}"
fi
log "stage=csv_import status=ok"
log "stage=csv_import status=completed"
log "upload_report=${UPLOAD_REPORT}"
log "import_report=${IMPORT_REPORT}"
