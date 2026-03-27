#!/usr/bin/env bash
# ==============================================================================
# Standalone runner for testing outside Home Assistant
# Usage: ./run_standalone.sh <server_hostname> <chargepoint_id> <password>
# ==============================================================================

set -euo pipefail

NO_TLS=false
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--no-tls" ]]; then
        NO_TLS=true
    else
        ARGS+=("$arg")
    fi
done

if [[ ${#ARGS[@]} -lt 3 ]]; then
    echo "Usage: $0 [--no-tls] <server_hostname> <chargepoint_id> <password>"
    echo ""
    echo "Example: $0 ocpp.example.com CP001 mysecretpassword"
    echo "         $0 --no-tls localhost:8765 CP001 mysecretpassword"
    exit 1
fi

export IO_SERVER_HOSTNAME="${ARGS[0]}"
export IO_CHARGEPOINT_ID="${ARGS[1]}"
export IO_PASSWORD="${ARGS[2]}"
export IO_USE_TLS="$( [[ "$NO_TLS" == "true" ]] && echo "false" || echo "true" )"
export IO_CHARGER_MODEL="${IO_CHARGER_MODEL:-PLP2-0-2-2}"
export IO_CHARGER_VENDOR="${IO_CHARGER_VENDOR:-Wall Box Chargers}"
export IO_CHARGER_SERIAL="${IO_CHARGER_SERIAL:-}"
export IO_FIRMWARE_VERSION="${IO_FIRMWARE_VERSION:-6.11.16}"
export IO_CURRENT_AMPS="${IO_CURRENT_AMPS:-32}"
export IO_LOG_LEVEL="${IO_LOG_LEVEL:-debug}"
export SUPERVISOR_TOKEN=""

# Use /tmp for persistence files when running standalone
export IO_DATA_DIR="${IO_DATA_DIR:-/tmp/ocpp_charge_proxy_data}"
mkdir -p "$IO_DATA_DIR"

echo "========================================"
echo "OCPP Charge Proxy - Standalone Mode"
echo "========================================"
echo "Server:       $IO_SERVER_HOSTNAME"
echo "Chargepoint:  $IO_CHARGEPOINT_ID"
echo "Model:        $IO_CHARGER_MODEL / $IO_CHARGER_VENDOR"
echo "Current:      ${IO_CURRENT_AMPS}A"
echo "Log level:    $IO_LOG_LEVEL"
echo "TLS:          $IO_USE_TLS"
echo "Data dir:     $IO_DATA_DIR"
echo "========================================"
echo ""

python3 -m src
