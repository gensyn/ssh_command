#!/usr/bin/env bash
# entrypoint.sh — startup script for the Playwright E2E test-runner container.
#
# 1. Waits for Home Assistant to become reachable.
# 2. Runs the HA onboarding flow to create the admin user if it has not been
#    created yet (first run of the named ha_config volume).
# 3. Hands off to pytest.

set -euo pipefail

HA_URL="${HOMEASSISTANT_URL:-http://homeassistant:8123}"
HA_USER="${HA_USERNAME:-admin}"
HA_PASS="${HA_PASSWORD:-admin}"
RESULTS_DIR="/app/playwright-results"

log() { echo "[entrypoint] $*"; }

mkdir -p "${RESULTS_DIR}"

# ── 1. Wait for Home Assistant to respond ────────────────────────────────────
log "Waiting for Home Assistant at ${HA_URL} …"
ATTEMPT=0
MAX_ATTEMPTS=120
until HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${HA_URL}/api/onboarding" 2>/dev/null) && \
      [[ "${HTTP}" =~ ^[2-4][0-9]{2}$ ]]; do
    ATTEMPT=$(( ATTEMPT + 1 ))
    if [[ "${ATTEMPT}" -ge "${MAX_ATTEMPTS}" ]]; then
        log "ERROR: Home Assistant did not become ready after ${MAX_ATTEMPTS} attempts."
        exit 1
    fi
    log "  Attempt ${ATTEMPT}/${MAX_ATTEMPTS} (HTTP ${HTTP:-000}), retrying in 5 s …"
    sleep 5
done
log "Home Assistant is responding."

# ── 2. Onboarding (create admin user on first start) ─────────────────────────
ONBOARDING=$(curl -sf "${HA_URL}/api/onboarding" 2>/dev/null || echo '[]')

# Check whether the "user" step is already done.
USER_DONE=$(_ONBOARDING="${ONBOARDING}" python3 - <<'PYEOF'
import json, os
try:
    data = json.loads(os.environ.get("_ONBOARDING", "[]"))
    print("true" if any(s.get("step") == "user" and s.get("done") for s in data) else "false")
except Exception:
    print("true")   # assume already set up if we can't parse
PYEOF
)

if [[ "${USER_DONE}" == "false" ]]; then
    log "Running HA onboarding — creating admin user '${HA_USER}' …"
    PAYLOAD="{\"client_id\":\"${HA_URL}/\",\"name\":\"Admin\",\"username\":\"${HA_USER}\",\"password\":\"${HA_PASS}\",\"language\":\"en\"}"
    RESPONSE=$(curl -sf -X POST "${HA_URL}/api/onboarding/users" \
        -H "Content-Type: application/json" \
        -d "${PAYLOAD}" 2>&1) || {
        log "WARNING: Onboarding request failed (HA may already be onboarded): ${RESPONSE}"
    }
    log "Onboarding complete."
    # Give HA a moment to settle after onboarding
    sleep 5
fi

# ── 3. Run the test suite ─────────────────────────────────────────────────────
log "Starting Playwright E2E test suite …"
cd /app
exec pytest tests/playwright/ \
    --tb=short \
    -v \
    --junitxml="${RESULTS_DIR}/junit.xml" \
    "$@"

