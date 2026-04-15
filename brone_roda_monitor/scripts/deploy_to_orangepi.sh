#!/bin/bash
# ==============================================================
# Deploy updated orange_tcp_bridge.py to Orange Pi
# ==============================================================
# Copies the modified bridge script to the Orange Pi via SCP.
#
# Usage:
#   ./deploy_to_orangepi.sh
#   ./deploy_to_orangepi.sh --ip 192.168.1.100
# ==============================================================

set -e

PURPLE='\033[0;35m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

ROBOT_USER="orange"
ROBOT_IP="10.42.0.247"

# Parse args
for arg in "$@"; do
    case $arg in
        --ip)   shift; ROBOT_IP="$1"; shift ;;
        --ip=*) ROBOT_IP="${arg#*=}" ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="${SCRIPT_DIR}/../../../Documents/Omnidirectional-Robot-Digital-Twin-Interface/orange_pi/orange_tcp_bridge.py"

# Fallback: check relative to brone_roda_monitor
if [ ! -f "$SOURCE_FILE" ]; then
    SOURCE_FILE="/home/codename-hydra/Documents/Omnidirectional-Robot-Digital-Twin-Interface/orange_pi/orange_tcp_bridge.py"
fi

echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${PURPLE}   📡  Deploy Bridge → Orange Pi${NC}"
echo -e "${BOLD}${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${CYAN}[1/3]${NC} Source file: ${SOURCE_FILE}"
if [ ! -f "$SOURCE_FILE" ]; then
    echo -e "${YELLOW}✗ File not found!${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Found"

echo -e "${CYAN}[2/3]${NC} Uploading to ${ROBOT_USER}@${ROBOT_IP}:~/orange_tcp_bridge.py ..."
scp "$SOURCE_FILE" "${ROBOT_USER}@${ROBOT_IP}:~/orange_tcp_bridge.py"
echo -e "  ${GREEN}✓${NC} Upload complete"

echo -e "${CYAN}[3/3]${NC} Restarting bridge on Orange Pi..."
echo -e "  ${YELLOW}⚠ Menghentikan bridge lama dan menjalankan ulang...${NC}"
ssh -t "${ROBOT_USER}@${ROBOT_IP}" "
    pkill -f orange_tcp_bridge.py 2>/dev/null || true
    sleep 1
    echo '--- Restarting bridge ---'
    source /opt/ros/humble/setup.bash
    export ROS_DOMAIN_ID=10
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export CYCLONEDDS_URI=file:///home/orange/NVME/Brone/Code/cyclonedds.xml
    export ROS_DISABLE_TYPE_HASH_CHECK=1
    echo 'orange' | sudo -S chmod 666 /dev/ttyUSB0
    nohup python3 ~/orange_tcp_bridge.py > ~/bridge.log 2>&1 &
    sleep 2
    echo '--- Bridge status ---'
    if pgrep -f orange_tcp_bridge.py > /dev/null; then
        echo '✓ Bridge running'
        tail -5 ~/bridge.log
    else
        echo '✗ Bridge failed to start'
        cat ~/bridge.log
    fi
"

echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}   ✅  Deploy selesai!${NC}"
echo -e "${BOLD}${GREEN}   Sekarang jalankan: test_gamepad.sh${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
