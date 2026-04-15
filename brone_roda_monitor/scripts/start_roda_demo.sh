#!/bin/bash
# ==============================================================
# BRone Roda Monitor — Demo Mode
# ==============================================================
# Launches dashboard + dummy data publisher.
# No robot hardware or Orange Pi required!
#
# Usage:
#   ./start_roda_demo.sh
# ==============================================================

set -e

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
    echo -e "${YELLOW}━━━ Shutting down demo...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo -e "  ${RED}✗${NC} Stopped PID $pid"
        fi
    done
    wait 2>/dev/null
    echo -e "${GREEN}Demo stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${PURPLE}   🛞  BRONE RODA MONITOR — DEMO MODE 🎮${NC}"
echo -e "${BOLD}${PURPLE}   Visualisasi dengan data dummy${NC}"
echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Source ROS2
echo -e "${BLUE}[1/3]${NC} Sourcing ROS2 environment..."
source /opt/ros/jazzy/setup.bash
source ~/robotis_ws/install/local_setup.bash
echo -e "  ${GREEN}✓${NC} ROS2 Jazzy ready"

# Launch demo publisher
echo -e "${PURPLE}[2/3]${NC} Starting demo data publisher..."
ros2 run brone_roda_monitor roda_demo_publisher &
PIDS+=($!)
sleep 1
echo -e "  ${GREEN}✓${NC} Demo publisher (PID: ${PIDS[-1]})"
echo -e "      Publishing: /brone/power/summary"

# Launch dashboard
echo -e "${CYAN}[3/3]${NC} Starting Roda Dashboard..."
ros2 run brone_roda_monitor roda_dashboard &
PIDS+=($!)
sleep 2
echo -e "  ${GREEN}✓${NC} Dashboard (PID: ${PIDS[-1]})"

echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}   🎮  DEMO READY!${NC}"
echo -e "${BOLD}${GREEN}   Open: http://localhost:8081${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Data dummy berfluktuasi otomatis (sine wave pattern)"
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop"
echo ""

wait
