#!/bin/bash
# ==============================================================
# BRone Roda — Production Motion Test
# ==============================================================
# Connects to Orange Pi via CycloneDDS, then runs motion test:
#   Forward → Backward → Strafe R → Strafe L → Spin CW → Spin CCW → Diagonal
#
# Also launches dashboard so you can watch telemetry while testing.
#
# Usage:
#   ./test_roda_motion.sh                     # Default IP, loop mode
#   ./test_roda_motion.sh --ip 192.168.1.100  # Custom IP
#   ./test_roda_motion.sh --no-loop           # Single cycle then stop
#   ./test_roda_motion.sh --speed 0.1         # Slower speed (m/s)
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
LOOP="true"
SPEED="0.15"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --ip)       ROBOT_IP="$2"; shift 2 ;;
        --ip=*)     ROBOT_IP="${1#*=}"; shift ;;
        --no-loop)  LOOP="false"; shift ;;
        --speed)    SPEED="$2"; shift 2 ;;
        --speed=*)  SPEED="${1#*=}"; shift ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --ip <IP>     Orange Pi IP (default: 10.42.0.247)"
            echo "  --speed <V>   Linear speed in m/s (default: 0.15)"
            echo "  --no-loop     Run once then stop (default: loop)"
            echo "  -h, --help    Show this help"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cleanup() {
    echo ""
    echo -e "${YELLOW}━━━ Emergency STOP & shutdown...${NC}"
    # Kill all child processes FIRST
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo -e "  ${RED}✗${NC} Stopped PID $pid"
        fi
    done
    # Quick safety stop with timeout
    timeout 2s ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
        '{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' 2>/dev/null &
    sleep 1
    kill 0 2>/dev/null || true
    wait 2>/dev/null
    echo -e "${GREEN}🛑 Robot stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${PURPLE}   🛞  BRONE RODA — MOTION TEST${NC}"
echo -e "${BOLD}${PURPLE}   Test gerak robot: maju/mundur/kiri/kanan/putar${NC}"
echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Step 1: Source ROS2
echo -e "${BLUE}[1/5]${NC} Sourcing ROS2 environment..."
source /opt/ros/jazzy/setup.bash
source ~/robotis_ws/install/local_setup.bash
echo -e "  ${GREEN}✓${NC} ROS2 Jazzy ready"

# Step 2: CycloneDDS
echo -e "${BLUE}[2/5]${NC} Configuring CycloneDDS..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CYCLONE_CFG="${SCRIPT_DIR}/../config/cyclonedds_roda.xml"
if [ ! -f "$CYCLONE_CFG" ]; then
    PKG_SHARE=$(ros2 pkg prefix brone_roda_monitor 2>/dev/null)/share/brone_roda_monitor
    CYCLONE_CFG="${PKG_SHARE}/config/cyclonedds_roda.xml"
fi
if [ -f "$CYCLONE_CFG" ]; then
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export CYCLONEDDS_URI="file://${CYCLONE_CFG}"
    echo -e "  ${GREEN}✓${NC} CycloneDDS → ${ROBOT_IP}"
else
    echo -e "  ${YELLOW}⚠${NC} No CycloneDDS config, using default discovery"
fi

export ROS_DOMAIN_ID=10
export ROS_DISABLE_TYPE_HASH_CHECK=1
echo -e "  ${GREEN}✓${NC} ROS_DOMAIN_ID = ${BOLD}10${NC}"

# Step 3: Launch telemetry
echo -e "${PURPLE}[3/5]${NC} Starting telemetry node..."
ros2 run brone_roda_monitor roda_telemetry --ros-args -p robot_ip:="${ROBOT_IP}" &
PIDS+=($!)
sleep 1
echo -e "  ${GREEN}✓${NC} Telemetry (PID: ${PIDS[-1]})"

# Step 4: Launch dashboard
echo -e "${CYAN}[4/5]${NC} Starting dashboard..."
ros2 run brone_roda_monitor roda_dashboard &
PIDS+=($!)
sleep 2
echo -e "  ${GREEN}✓${NC} Dashboard → http://localhost:8081"

# Step 5: Launch motion test
echo -e "${YELLOW}[5/5]${NC} Starting motion test..."
echo ""
echo -e "  ${BOLD}${RED}⚠️  ROBOT AKAN BERGERAK!${NC}"
echo -e "  ${RED}Pastikan area sekitar robot AMAN.${NC}"
echo -e "  ${RED}Tekan Ctrl+C kapan saja untuk EMERGENCY STOP.${NC}"
echo ""
echo -e "  Menunggu 3 detik..."
sleep 3

ros2 run brone_roda_monitor roda_motion_test \
    --ros-args -p speed:="${SPEED}" -p loop:="${LOOP}" &
PIDS+=($!)
echo -e "  ${GREEN}✓${NC} Motion test (PID: ${PIDS[-1]})"

echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}   🛞  TEST RUNNING${NC}"
echo -e "${BOLD}${GREEN}   Dashboard: http://localhost:8081${NC}"
echo -e "${BOLD}${GREEN}   Speed: ${SPEED} m/s | Loop: ${LOOP}${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}${RED}Ctrl+C = EMERGENCY STOP${NC}"
echo ""

wait
