#!/bin/bash
# ==============================================================
# BRONE Unified Dashboard — One-Click Launcher
# ==============================================================
# Launches:
#   1. OP3 power_monitor_node  (if --op3 or --all)
#   2. BRone roda_telemetry    (if --roda or --all)
#   3. unified_dashboard       (always)
#
# Usage:
#   ./start_unified.sh          # Dashboard only
#   ./start_unified.sh --op3    # Dashboard + OP3 telemetry
#   ./start_unified.sh --roda   # Dashboard + Roda telemetry
#   ./start_unified.sh --all    # Everything
# ==============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

PIDS=()

cleanup() {
    echo ""
    echo -e "${YELLOW}━━━ Shutting down all processes...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo -e "  ${RED}✗${NC} Stopped PID $pid"
        fi
    done
    wait 2>/dev/null
    echo -e "${GREEN}All processes stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Parse args
LAUNCH_OP3=false
LAUNCH_RODA=false

for arg in "$@"; do
    case $arg in
        --op3)  LAUNCH_OP3=true ;;
        --roda) LAUNCH_RODA=true ;;
        --all)  LAUNCH_OP3=true; LAUNCH_RODA=true ;;
        -h|--help)
            echo "Usage: $0 [--op3] [--roda] [--all]"
            echo "  --op3   Launch OP3 power_monitor_node"
            echo "  --roda  Launch BRone roda_telemetry node"
            echo "  --all   Launch both telemetry nodes"
            echo "  (none)  Launch dashboard only"
            exit 0
            ;;
    esac
done

# Source ROS2
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${CYAN}   BRONE UNIFIED DASHBOARD — LAUNCHER${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BLUE}[1/4]${NC} Sourcing ROS2 environment..."
source /opt/ros/jazzy/setup.bash
source ~/robotis_ws/install/local_setup.bash
echo -e "  ${GREEN}✓${NC} ROS2 Jazzy ready"

# Launch OP3 telemetry
if [ "$LAUNCH_OP3" = true ]; then
    echo -e "${BLUE}[2/4]${NC} Starting OP3 power_monitor_node..."
    ros2 run op3_power_monitor power_monitor_node &
    PIDS+=($!)
    sleep 1
    echo -e "  ${GREEN}✓${NC} OP3 telemetry (PID: ${PIDS[-1]})"
else
    echo -e "${BLUE}[2/4]${NC} Skipping OP3 telemetry${NC} (add --op3 to enable)"
fi

# Launch Roda telemetry
if [ "$LAUNCH_RODA" = true ]; then
    echo -e "${PURPLE}[3/4]${NC} Starting BRone roda_telemetry..."
    ros2 run brone_roda_monitor roda_telemetry &
    PIDS+=($!)
    sleep 1
    echo -e "  ${GREEN}✓${NC} Roda telemetry (PID: ${PIDS[-1]})"
else
    echo -e "${PURPLE}[3/4]${NC} Skipping Roda telemetry${NC} (add --roda to enable)"
fi

# Launch unified dashboard (always)
echo -e "${CYAN}[4/4]${NC} Starting Unified Dashboard..."
ros2 run op3_power_monitor unified_dashboard &
PIDS+=($!)
sleep 2
echo -e "  ${GREEN}✓${NC} Dashboard (PID: ${PIDS[-1]})"

echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}   🌐  DASHBOARD READY${NC}"
echo -e "${BOLD}${GREEN}   Open: http://localhost:8080${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop all services"
echo ""

# Wait for all
wait
