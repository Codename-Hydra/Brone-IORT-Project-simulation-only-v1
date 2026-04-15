#!/bin/bash
# ==============================================================
# BRone Roda Monitor — Production Launcher
# ==============================================================
# Connects to the real robot on Orange Pi via CycloneDDS.
# Launches:
#   1. roda_telemetry  (subscribe to real robot topics)
#   2. roda_dashboard  (HTTP 8081 + WS 9091)
#
# Usage:
#   ./start_roda.sh                          # Default IP
#   ./start_roda.sh --ip 192.168.1.100       # Custom robot IP
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
ROBOT_IP="10.42.0.247"

# Parse args
for arg in "$@"; do
    case $arg in
        --ip)   shift; ROBOT_IP="$1"; shift ;;
        --ip=*) ROBOT_IP="${arg#*=}" ;;
        -h|--help)
            echo "Usage: $0 [--ip <ROBOT_IP>]"
            echo "  --ip   Orange Pi IP address (default: 10.42.0.247)"
            exit 0
            ;;
    esac
done

cleanup() {
    echo ""
    echo -e "${YELLOW}━━━ Shutting down BRone Roda...${NC}"
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

echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${PURPLE}   🛞  BRONE RODA MONITOR — PRODUCTION MODE${NC}"
echo -e "${BOLD}${PURPLE}   Koneksi ke robot di Orange Pi${NC}"
echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Step 1: Source ROS2
echo -e "${BLUE}[1/4]${NC} Sourcing ROS2 environment..."
source /opt/ros/jazzy/setup.bash
source ~/robotis_ws/install/local_setup.bash
echo -e "  ${GREEN}✓${NC} ROS2 Jazzy ready"

# Step 2: Setup CycloneDDS for peer-to-peer discovery
echo -e "${BLUE}[2/4]${NC} Configuring CycloneDDS peer discovery..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CYCLONE_CFG="${SCRIPT_DIR}/../config/cyclonedds_roda.xml"

# Also check installed path
if [ ! -f "$CYCLONE_CFG" ]; then
    PKG_SHARE=$(ros2 pkg prefix brone_roda_monitor 2>/dev/null)/share/brone_roda_monitor
    CYCLONE_CFG="${PKG_SHARE}/config/cyclonedds_roda.xml"
fi

if [ -f "$CYCLONE_CFG" ]; then
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export CYCLONEDDS_URI="file://${CYCLONE_CFG}"
    echo -e "  ${GREEN}✓${NC} CycloneDDS config: ${CYCLONE_CFG}"
    echo -e "  ${GREEN}✓${NC} RMW: rmw_cyclonedds_cpp"
else
    echo -e "  ${YELLOW}⚠${NC} CycloneDDS config not found, using default DDS discovery"
fi

export ROS_DOMAIN_ID=10
export ROS_DISABLE_TYPE_HASH_CHECK=1
echo -e "  ${GREEN}✓${NC} ROS_DOMAIN_ID = ${BOLD}10${NC}"
echo -e "  ${CYAN}🤖${NC} Robot IP: ${BOLD}${ROBOT_IP}${NC}"

# Step 3: Launch telemetry node
echo -e "${PURPLE}[3/4]${NC} Starting roda_telemetry node..."
ros2 run brone_roda_monitor roda_telemetry --ros-args -p robot_ip:="${ROBOT_IP}" &
PIDS+=($!)
sleep 1
echo -e "  ${GREEN}✓${NC} Telemetry (PID: ${PIDS[-1]})"
echo -e "      Subscribed: /cmd_vel, /brone/wheel_states"
echo -e "      Publishing: /brone/power/summary (5 Hz)"
echo -e "      Ping target: ${ROBOT_IP}"

# Step 4: Launch dashboard node
echo -e "${CYAN}[4/4]${NC} Starting roda_dashboard..."
ros2 run brone_roda_monitor roda_dashboard &
PIDS+=($!)
sleep 2
echo -e "  ${GREEN}✓${NC} Dashboard (PID: ${PIDS[-1]})"

echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}   🛞  BRONE RODA READY!${NC}"
echo -e "${BOLD}${GREEN}   Dashboard: http://localhost:8081${NC}"
echo -e "${BOLD}${GREEN}   Robot IP:  ${ROBOT_IP}${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${PURPLE}🛞 Dashboard${NC} → http://localhost:8081"
echo -e "  ${CYAN}📡 WebSocket${NC} → ws://localhost:9091"
echo -e "  ${BLUE}🤖 Orange Pi${NC} → ${ROBOT_IP}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop"
echo ""

wait
